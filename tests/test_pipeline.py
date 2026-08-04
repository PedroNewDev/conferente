"""Teste de integração: o ciclo completo sobre os 15 XMLs do gerador.

Cada cenário deve terminar exatamente com o status e as ocorrências previstos
na tabela de cenários do gerador.
"""
from decimal import Decimal
from pathlib import Path

from app.models import ContaPagar, MovimentoEstoque, NotaFiscal, PedidoCompra, Produto
from app.services.pipeline import executar_ciclo
from scripts.gerar_notas_teste import gerar_todos


def _nota(db, empresa, numero: int) -> NotaFiscal:
    return db.query(NotaFiscal).filter_by(empresa_id=empresa.id, numero=numero).one()


def _tipos(nota: NotaFiscal) -> set[str]:
    return {o.tipo for o in nota.ocorrencias}


def _produto(db, empresa, codigo: str) -> Produto:
    return db.query(Produto).filter_by(empresa_id=empresa.id, codigo_interno=codigo).one()


def test_ciclo_completo(db, empresa, fonte, tmp_path):
    gerar_todos(Path(fonte.entrada))
    resumo = executar_ciclo(db, empresa.id, fonte)

    assert resumo.documentos_lidos == 15
    assert resumo.notas_novas == 13          # 06 é duplicata, 13 é corrompido
    assert resumo.duplicatas_descartadas == 1
    assert resumo.quarentena == 1
    assert resumo.aprovadas == 7             # 01, 05, 10, 11, 12, 14, 15
    assert resumo.bloqueadas == 3            # 02, 03, 04
    assert resumo.rejeitadas == 3            # 07, 08, 09
    assert resumo.erros == []

    # 01 — nota perfeita
    n01 = _nota(db, empresa, 90001)
    assert n01.status == "aprovada"
    assert n01.pedido.numero == "PC-1001"

    # 02 — preço acima: P02 com impacto (7.45-6.90)*100
    n02 = _nota(db, empresa, 90002)
    assert n02.status == "bloqueada"
    assert "P02" in _tipos(n02)
    oc_p02 = next(o for o in n02.ocorrencias if o.tipo == "P02")
    assert Decimal(oc_p02.valor_impacto) == Decimal("55.00")

    # 03 — quantidade acima: P04
    n03 = _nota(db, empresa, 90003)
    assert n03.status == "bloqueada"
    assert "P04" in _tipos(n03)

    # 04 — item fora do pedido: P06
    n04 = _nota(db, empresa, 90004)
    assert n04.status == "bloqueada"
    assert "P06" in _tipos(n04)

    # 05 — entrega parcial: aprovada, P05, pedido parcial
    n05 = _nota(db, empresa, 90005)
    assert n05.status == "aprovada"
    assert "P05" in _tipos(n05)
    pc1004 = db.query(PedidoCompra).filter_by(empresa_id=empresa.id, numero="PC-1004").one()
    assert pc1004.status == "parcial"

    # 06 — duplicata da 01: V12 na nota original, sem nova nota
    assert "V12" in _tipos(n01)
    assert db.query(NotaFiscal).filter_by(empresa_id=empresa.id, chave=n01.chave).count() == 1

    # 07 — chave adulterada: V02
    n07 = _nota(db, empresa, 90007)
    assert n07.status == "rejeitada"
    assert "V02" in _tipos(n07)

    # 08 — soma divergente: V08
    n08 = _nota(db, empresa, 90008)
    assert n08.status == "rejeitada"
    assert "V08" in _tipos(n08)

    # 09 — outro destinatário: V06
    n09 = _nota(db, empresa, 90009)
    assert n09.status == "rejeitada"
    assert "V06" in _tipos(n09)

    # 10 — fornecedor novo: C01, fornecedor criado inativo
    n10 = _nota(db, empresa, 90010)
    assert n10.status == "aprovada"
    assert "C01" in _tipos(n10)
    assert n10.fornecedor.ativo is False

    # 11 — sem pedido: P01
    n11 = _nota(db, empresa, 90011)
    assert n11.status == "aprovada"
    assert "P01" in _tipos(n11)

    # 12 — devolução: sem efeito no estoque
    n12 = _nota(db, empresa, 90012)
    assert n12.tipo_operacao == "devolucao"
    assert db.query(MovimentoEstoque).filter_by(
        empresa_id=empresa.id, origem_id=n12.id).count() == 0

    # 13 — corrompido: quarentena com o motivo gravado
    assert (fonte.quarentena / "13_xml_corrompido.xml").exists()
    assert resumo.ocorrencias_por_tipo.get("V01") == 1

    # 14 — sem duplicatas: conta única arbitrada (F01)
    n14 = _nota(db, empresa, 90014)
    assert n14.status == "aprovada"
    contas_14 = db.query(ContaPagar).filter_by(nota_id=n14.id).all()
    assert len(contas_14) == 1
    assert contas_14[0].valor == Decimal("1258.00")
    assert "F01" in _tipos(n14)

    # 15 — sem de-para: C02, sem movimento
    n15 = _nota(db, empresa, 90015)
    assert n15.status == "aprovada"
    assert "C02" in _tipos(n15)
    assert db.query(MovimentoEstoque).filter_by(
        empresa_id=empresa.id, origem_id=n15.id).count() == 0

    # Estoque: notas aprovadas subiram o saldo na quantidade correta
    assert _produto(db, empresa, "ARZ-5").estoque_atual == Decimal("50")
    assert _produto(db, empresa, "FEJ-1").estoque_atual == Decimal("80")
    assert _produto(db, empresa, "OLE-900").estoque_atual == Decimal("100")
    det = _produto(db, empresa, "DET-500")
    assert det.estoque_atual == Decimal("95")   # 45 da nota 05 + 50 da nota 11
    # custo médio ponderado: (45*2.15 + 50*2.10) / 95
    assert det.custo_medio == Decimal("2.1237")

    # Contas a pagar da nota 01: duas parcelas das duplicatas
    contas_01 = db.query(ContaPagar).filter_by(nota_id=n01.id).all()
    assert len(contas_01) == 2
    assert sum(c.valor for c in contas_01) == n01.valor_total

    # Pedido PC-1001 totalmente atendido
    pc1001 = db.query(PedidoCompra).filter_by(empresa_id=empresa.id, numero="PC-1001").one()
    assert pc1001.status == "atendido"

    # Impacto financeiro somado: P02 (55.00) + P04 ((150-120)*4.85 = 145.50)
    assert resumo.impacto_divergencias == Decimal("200.50")

    # Relatório do ciclo foi gerado (PDF ou HTML conforme a máquina)
    relatorios = list(Path("relatorios").glob("ciclo_*"))
    assert len(relatorios) == 1
