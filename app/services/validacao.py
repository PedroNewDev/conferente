"""Regras de validação estrutural/fiscal (V02–V11) e de cadastro (C01–C03).

Cada regra grava uma `ocorrencia` vinculada à nota. A V01 (parse) e a V12
(duplicidade) são tratadas no pipeline, antes da nota existir.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.enums import Severidade
from app.models import Fornecedor, NotaFiscal, NotaItem, Ocorrencia, Parametro, ProdutoFornecedor
from app.services.nfe_parser import NotaFiscalNFe
from app.utils.chave_nfe import chave_valida, decompoe_chave
from app.utils.documentos import cnpj_valido
from app.utils.numeros import dentro_da_tolerancia


def registrar_ocorrencia(db: Session, empresa_id: int, tipo: str, severidade: Severidade,
                         mensagem: str, nota: NotaFiscal | None = None,
                         nota_item: NotaItem | None = None, detalhe: dict | None = None,
                         valor_impacto: Decimal | None = None) -> Ocorrencia:
    """Toda decisão automática passa por aqui — nenhum bloqueio sem motivo gravado."""
    oc = Ocorrencia(
        empresa_id=empresa_id,
        nota_id=nota.id if nota else None,
        nota_item_id=nota_item.id if nota_item else None,
        tipo=tipo,
        severidade=severidade.value,
        mensagem=mensagem,
        detalhe=detalhe,
        valor_impacto=valor_impacto,
    )
    db.add(oc)
    db.flush()
    return oc


def tem_bloqueante(ocorrencias: list[Ocorrencia]) -> bool:
    return any(o.severidade == Severidade.BLOQUEANTE.value and not o.resolvida
               for o in ocorrencias)


def validar_nota(db: Session, empresa_cnpj: str, parametro: Parametro,
                 nfe: NotaFiscalNFe, nota: NotaFiscal) -> list[Ocorrencia]:
    """Aplica V02 a V11. Devolve as ocorrências geradas."""
    ocorrencias: list[Ocorrencia] = []
    empresa_id = nota.empresa_id
    tol_abs = Decimal(parametro.tolerancia_valor_absoluto)

    def reg(tipo: str, sev: Severidade, msg: str, detalhe: dict | None = None) -> None:
        ocorrencias.append(registrar_ocorrencia(db, empresa_id, tipo, sev, msg,
                                                nota=nota, detalhe=detalhe))

    # V02 — dígito verificador da chave
    if not chave_valida(nfe.chave):
        reg("V02", Severidade.BLOQUEANTE,
            "Dígito verificador da chave de acesso inválido. "
            "A chave pode ter sido adulterada.",
            {"chave": nfe.chave})
    else:
        # V03 — campos embutidos na chave x tags do XML (só faz sentido com chave íntegra)
        partes = decompoe_chave(nfe.chave)
        aamm_xml = nfe.data_emissao.strftime("%y%m")
        divergencias = {}
        if partes["cnpj_emitente"] != nfe.cnpj_emitente:
            divergencias["cnpj_emitente"] = {"chave": partes["cnpj_emitente"], "xml": nfe.cnpj_emitente}
        if int(partes["numero"]) != nfe.numero:
            divergencias["numero"] = {"chave": partes["numero"], "xml": nfe.numero}
        if int(partes["serie"]) != nfe.serie:
            divergencias["serie"] = {"chave": partes["serie"], "xml": nfe.serie}
        if partes["modelo"] != nfe.modelo:
            divergencias["modelo"] = {"chave": partes["modelo"], "xml": nfe.modelo}
        if partes["aamm"] != aamm_xml:
            divergencias["aamm"] = {"chave": partes["aamm"], "xml": aamm_xml}
        if divergencias:
            reg("V03", Severidade.BLOQUEANTE,
                "Campos embutidos na chave divergem das tags do XML.",
                divergencias)

    # V04 — CNPJ do emitente
    if not cnpj_valido(nfe.cnpj_emitente):
        reg("V04", Severidade.BLOQUEANTE,
            f"CNPJ do emitente inválido: {nfe.cnpj_emitente}.")

    # V05 — CNPJ do destinatário (quando for CNPJ; CPF não é validado aqui)
    if nfe.cnpj_destinatario and len(nfe.cnpj_destinatario) == 14 \
            and not cnpj_valido(nfe.cnpj_destinatario):
        reg("V05", Severidade.BLOQUEANTE,
            f"CNPJ do destinatário inválido: {nfe.cnpj_destinatario}.")

    # V06 — destinatário deve ser a empresa
    if nfe.cnpj_destinatario != empresa_cnpj:
        reg("V06", Severidade.BLOQUEANTE,
            "O destinatário da nota não é esta empresa. "
            "Confira se a nota foi enviada para a caixa correta.",
            {"destinatario": nfe.cnpj_destinatario, "empresa": empresa_cnpj})

    # V07 — soma dos itens x total de produtos
    soma_itens = sum((i.valor_total for i in nfe.itens), Decimal("0"))
    if not dentro_da_tolerancia(soma_itens, nfe.valor_produtos, tol_abs):
        reg("V07", Severidade.BLOQUEANTE,
            "A soma dos itens não confere com o total de produtos da nota.",
            {"soma_itens": str(soma_itens), "valor_produtos": str(nfe.valor_produtos)})

    # V08 — recomposição do total da nota.
    # Fórmula simplificada para o escopo (a oficial tem mais componentes):
    # vProd - vDesc + vST + vFrete + vSeg + vOutro + vIPI == vNF
    recomposto = (nfe.valor_produtos - nfe.valor_desconto + nfe.valor_st
                  + nfe.valor_frete + nfe.valor_seguro + nfe.valor_outros + nfe.valor_ipi)
    if not dentro_da_tolerancia(recomposto, nfe.valor_total, tol_abs):
        reg("V08", Severidade.BLOQUEANTE,
            "O valor total da nota não confere com a recomposição dos totais.",
            {"recomposto": str(recomposto), "vNF": str(nfe.valor_total)})

    # V09 — soma das duplicatas x total (alerta)
    if nfe.duplicatas:
        soma_dup = sum((d.valor for d in nfe.duplicatas), Decimal("0"))
        if not dentro_da_tolerancia(soma_dup, nfe.valor_total, tol_abs):
            reg("V09", Severidade.ALERTA,
                "A soma das duplicatas não confere com o total da nota.",
                {"soma_duplicatas": str(soma_dup), "vNF": str(nfe.valor_total)})

    # V10 — emissão no futuro
    agora = datetime.now(timezone.utc)
    if nfe.data_emissao > agora:
        reg("V10", Severidade.BLOQUEANTE,
            "Data de emissão no futuro.",
            {"data_emissao": nfe.data_emissao.isoformat()})

    # V11 — emissão retroativa além do limite
    limite = agora - timedelta(days=parametro.dias_max_emissao_retroativa)
    if nfe.data_emissao < limite:
        reg("V11", Severidade.ALERTA,
            f"Data de emissão anterior ao limite de "
            f"{parametro.dias_max_emissao_retroativa} dias.",
            {"data_emissao": nfe.data_emissao.isoformat()})

    return ocorrencias


def resolver_fornecedor(db: Session, empresa_id: int, nfe: NotaFiscalNFe,
                        nota: NotaFiscal) -> tuple[Fornecedor, list[Ocorrencia]]:
    """C01 — localiza o fornecedor pelo CNPJ do emitente; se não existir,
    cria automaticamente como inativo e registra a pendência."""
    ocorrencias: list[Ocorrencia] = []
    fornecedor = db.query(Fornecedor).filter_by(
        empresa_id=empresa_id, cnpj=nfe.cnpj_emitente).first()
    if fornecedor is None:
        fornecedor = Fornecedor(
            empresa_id=empresa_id,
            cnpj=nfe.cnpj_emitente,
            razao_social=nfe.nome_emitente or f"Fornecedor {nfe.cnpj_emitente}",
            uf=nfe.uf_emitente,
            municipio=nfe.municipio_emitente,
            ativo=False,
        )
        db.add(fornecedor)
        db.flush()
        ocorrencias.append(registrar_ocorrencia(
            db, empresa_id, "C01", Severidade.ALERTA,
            f"Emitente {nfe.nome_emitente} ({nfe.cnpj_emitente}) não estava "
            "cadastrado. Fornecedor criado como inativo — revise o cadastro.",
            nota=nota, detalhe={"fornecedor_id": fornecedor.id}))
    nota.fornecedor_id = fornecedor.id
    return fornecedor, ocorrencias


def resolver_produtos(db: Session, empresa_id: int, fornecedor: Fornecedor,
                      nota: NotaFiscal, itens: list[NotaItem]) -> list[Ocorrencia]:
    """C02/C03 — resolve cada item da nota para um produto via de-para."""
    ocorrencias: list[Ocorrencia] = []
    for item in itens:
        vinculo = db.query(ProdutoFornecedor).filter_by(
            empresa_id=empresa_id, fornecedor_id=fornecedor.id,
            codigo_no_fornecedor=item.codigo_fornecedor).first()
        if vinculo is None and item.ean:
            vinculo = db.query(ProdutoFornecedor).filter_by(
                empresa_id=empresa_id, fornecedor_id=fornecedor.id,
                ean=item.ean).first()
        if vinculo:
            item.produto_id = vinculo.produto_id
        else:
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "C02", Severidade.ALERTA,
                f"Item {item.n_item} ({item.codigo_fornecedor} — {item.descricao}) "
                "não tem de-para cadastrado para este fornecedor.",
                nota=nota, nota_item=item))

        if not item.ncm or len(item.ncm) != 8 or not item.ncm.isdigit():
            ocorrencias.append(registrar_ocorrencia(
                db, empresa_id, "C03", Severidade.INFORMATIVA,
                f"Item {item.n_item} com NCM ausente ou fora do formato de 8 dígitos.",
                nota=nota, nota_item=item, detalhe={"ncm": item.ncm}))
    return ocorrencias
