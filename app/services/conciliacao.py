"""Classificação por CFOP e conciliação da nota com o pedido de compra (P01–P09)."""
from collections import Counter
from decimal import Decimal

from sqlalchemy.orm import Session

from app.enums import Severidade, StatusPedido, TipoOperacao
from app.models import NotaFiscal, NotaItem, Ocorrencia, Parametro, PedidoCompra, PedidoItem
from app.services.validacao import registrar_ocorrencia
from app.utils.numeros import dentro_da_tolerancia

CFOPS_DEVOLUCAO = {"5202", "6202", "5411", "6411", "5553", "6553"}
CFOPS_BONIFICACAO = {"5910", "6910"}
CFOPS_REMESSA = {"5915", "6915", "5901", "6901", "5905", "6905"}
PREFIXOS_COMPRA = ("51", "52", "61", "62", "71", "72")


def classificar_cfop(itens: list[NotaItem]) -> tuple[str | None, str]:
    """Devolve (cfop_predominante, tipo_operacao). O predominante é o mais frequente."""
    cfops = [i.cfop for i in itens if i.cfop]
    if not cfops:
        return None, TipoOperacao.OUTRO.value
    predominante = Counter(cfops).most_common(1)[0][0]

    if predominante in CFOPS_DEVOLUCAO:
        tipo = TipoOperacao.DEVOLUCAO.value
    elif predominante in CFOPS_BONIFICACAO:
        tipo = TipoOperacao.BONIFICACAO.value
    elif predominante in CFOPS_REMESSA:
        tipo = TipoOperacao.REMESSA.value
    elif predominante.startswith(PREFIXOS_COMPRA):
        tipo = TipoOperacao.COMPRA.value
    else:
        tipo = TipoOperacao.OUTRO.value
    return predominante, tipo


def vincular_pedido(db: Session, empresa_id: int, nota: NotaFiscal,
                    itens: list[NotaItem],
                    numero_infcpl: str | None) -> PedidoCompra | None:
    """Estratégia de vínculo, em ordem de confiança; para na primeira que casa."""
    def busca(numero: str) -> PedidoCompra | None:
        return db.query(PedidoCompra).filter(
            PedidoCompra.empresa_id == empresa_id,
            PedidoCompra.numero == numero,
            PedidoCompra.fornecedor_id == nota.fornecedor_id,
        ).first()

    # 1. xPed dos itens
    for item in itens:
        if item.numero_pedido_xml:
            pedido = busca(item.numero_pedido_xml)
            if pedido:
                return pedido

    # 2. número extraído das informações complementares
    if numero_infcpl:
        pedido = busca(numero_infcpl)
        if pedido:
            return pedido

    # 3. único pedido em aberto do fornecedor que contenha todos os produtos
    #    identificados da nota
    produtos_nota = {i.produto_id for i in itens if i.produto_id}
    if produtos_nota:
        abertos = db.query(PedidoCompra).filter(
            PedidoCompra.empresa_id == empresa_id,
            PedidoCompra.fornecedor_id == nota.fornecedor_id,
            PedidoCompra.status.in_([StatusPedido.ABERTO.value, StatusPedido.PARCIAL.value]),
        ).all()
        candidatos = []
        for pedido in abertos:
            produtos_pedido = {pi.produto_id for pi in pedido.itens}
            if produtos_nota <= produtos_pedido:
                candidatos.append(pedido)
        if len(candidatos) == 1:
            return candidatos[0]

    return None


def conciliar(db: Session, empresa_id: int, parametro: Parametro, nota: NotaFiscal,
              itens: list[NotaItem], pedido: PedidoCompra | None) -> list[Ocorrencia]:
    """Aplica P01 a P08 comparando a nota, item a item, com o pedido vinculado.

    O impacto financeiro de P02/P04 é `valor_cobrado - valor_esperado`, gravado
    em `ocorrencia.valor_impacto` — é o número que o relatório soma.
    """
    ocorrencias: list[Ocorrencia] = []
    tol_abs = Decimal(parametro.tolerancia_valor_absoluto)
    tol_pct = Decimal(parametro.tolerancia_preco_percentual)

    # P01 — nenhum pedido vinculável
    if pedido is None:
        sev = Severidade.BLOQUEANTE if parametro.bloquear_sem_pedido else Severidade.ALERTA
        ocorrencias.append(registrar_ocorrencia(
            db, empresa_id, "P01", sev,
            "Nenhum pedido de compra vinculável foi encontrado para esta nota.",
            nota=nota))
        return ocorrencias

    nota.pedido_id = pedido.id

    # Casa cada item da nota com o item do pedido pelo produto resolvido no de-para.
    # Havendo mais de um item do pedido para o mesmo produto, usa o de maior
    # saldo pendente. Itens sem produto identificado já geraram C02 e ficam
    # fora da comparação.
    itens_pedido_por_produto: dict[int, list[PedidoItem]] = {}
    for pi in pedido.itens:
        itens_pedido_por_produto.setdefault(pi.produto_id, []).append(pi)

    produtos_entregues: set[int] = set()
    for item in itens:
        if not item.produto_id:
            continue
        candidatos = itens_pedido_por_produto.get(item.produto_id)
        if not candidatos:
            # P06 — item presente na nota e ausente no pedido
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "P06", Severidade.BLOQUEANTE,
                f"Item {item.n_item} ({item.descricao}) não consta do pedido "
                f"{pedido.numero}.",
                nota=nota, nota_item=item,
                detalhe={"pedido": pedido.numero}))
            continue

        pi = max(candidatos, key=lambda c: Decimal(c.quantidade) - Decimal(c.quantidade_atendida))
        item.pedido_item_id = pi.id
        produtos_entregues.add(item.produto_id)

        preco_pedido = Decimal(pi.preco_unitario)
        preco_nota = Decimal(item.valor_unitario)
        qtd_nota = Decimal(item.quantidade)
        saldo_pendente = Decimal(pi.quantidade) - Decimal(pi.quantidade_atendida)

        # P02 — preço acima da tolerância / P03 — preço abaixo
        if preco_nota > preco_pedido and not dentro_da_tolerancia(
                preco_nota, preco_pedido, tol_abs, tol_pct):
            impacto = ((preco_nota - preco_pedido) * qtd_nota).quantize(Decimal("0.01"))
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "P02", Severidade.BLOQUEANTE,
                f"Item {item.n_item} ({item.descricao}): preço {preco_nota} acima "
                f"do pedido ({preco_pedido}), além da tolerância.",
                nota=nota, nota_item=item,
                detalhe={"preco_nota": str(preco_nota), "preco_pedido": str(preco_pedido)},
                valor_impacto=impacto))
        elif preco_nota < preco_pedido:
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "P03", Severidade.INFORMATIVA,
                f"Item {item.n_item} ({item.descricao}): preço {preco_nota} abaixo "
                f"do pedido ({preco_pedido}).",
                nota=nota, nota_item=item))

        # P04 — quantidade acima do saldo pendente / P05 — entrega parcial
        tol_qtd = Decimal(parametro.tolerancia_quantidade_percentual)
        if qtd_nota > saldo_pendente and not dentro_da_tolerancia(
                qtd_nota, saldo_pendente, Decimal("0"), tol_qtd):
            impacto = ((qtd_nota - saldo_pendente) * preco_pedido).quantize(Decimal("0.01"))
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "P04", Severidade.BLOQUEANTE,
                f"Item {item.n_item} ({item.descricao}): quantidade {qtd_nota} maior "
                f"que o saldo pendente do pedido ({saldo_pendente}).",
                nota=nota, nota_item=item,
                detalhe={"quantidade": str(qtd_nota), "saldo_pendente": str(saldo_pendente)},
                valor_impacto=impacto))
        elif qtd_nota < saldo_pendente:
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "P05", Severidade.INFORMATIVA,
                f"Item {item.n_item} ({item.descricao}): entrega parcial "
                f"({qtd_nota} de {saldo_pendente}).",
                nota=nota, nota_item=item))

    # P07 — itens do pedido não entregues nesta nota
    for produto_id, pis in itens_pedido_por_produto.items():
        if produto_id in produtos_entregues:
            continue
        pendencia = sum((Decimal(pi.quantidade) - Decimal(pi.quantidade_atendida)
                         for pi in pis), Decimal("0"))
        if pendencia > 0:
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "P07", Severidade.INFORMATIVA,
                f"Produto do pedido {pedido.numero} sem entrega nesta nota "
                f"(saldo pendente {pendencia}).",
                nota=nota, detalhe={"produto_id": produto_id}))

    # P08 — frete acima do previsto
    frete_nota = Decimal(nota.valor_frete or 0)
    frete_previsto = Decimal(pedido.frete_previsto)
    if frete_nota > frete_previsto and not dentro_da_tolerancia(
            frete_nota, frete_previsto, tol_abs):
        ocorrencias.append(registrar_ocorrencia(
            db, empresa_id, "P08", Severidade.ALERTA,
            f"Frete cobrado ({frete_nota}) acima do previsto no pedido "
            f"({frete_previsto}).",
            nota=nota,
            detalhe={"frete_nota": str(frete_nota), "frete_previsto": str(frete_previsto)}))

    return ocorrencias


def sinalizar_cfop_nao_venda(db: Session, empresa_id: int, nota: NotaFiscal) -> Ocorrencia | None:
    """P09 — CFOP predominante fora de 5xxx/6xxx/7xxx."""
    cfop = nota.cfop_predominante
    if cfop and cfop[0] in ("5", "6", "7"):
        return None
    return registrar_ocorrencia(
        db, empresa_id, "P09", Severidade.ALERTA,
        f"CFOP predominante ({cfop}) não é de operação de venda. "
        f"Nota classificada como '{nota.tipo_operacao}'.",
        nota=nota, detalhe={"cfop": cfop})
