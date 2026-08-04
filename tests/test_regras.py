"""Um teste por regra do catálogo (V01–V12, C01–C03, P01–P09).

Cada teste monta o cenário mínimo com o gerador, roda o ciclo e afirma a
ocorrência esperada e o status resultante da nota.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from app.models import NotaFiscal, Parametro
from app.services.pipeline import executar_ciclo
from app.utils.chave_nfe import monta_chave
from scripts.gerar_notas_teste import (
    CNPJ_ALFA, CNPJ_GAMA, D, FUSO_SP, _it, montar_nota,
)

ONTEM = (datetime.now(FUSO_SP) - timedelta(days=1)).replace(microsecond=0)
ALFA = (CNPJ_ALFA, "Distribuidora Alfa de Alimentos LTDA")
GAMA = (CNPJ_GAMA, "Industria Gama de Produtos de Limpeza LTDA")


def _roda(db, empresa, fonte, nome: str, conteudo: bytes):
    (Path(fonte.entrada) / nome).write_bytes(conteudo)
    return executar_ciclo(db, empresa.id, fonte)


def _unica_nota(db, empresa) -> NotaFiscal:
    return db.query(NotaFiscal).filter_by(empresa_id=empresa.id).one()


def _tipos(nota: NotaFiscal) -> set[str]:
    return {o.tipo for o in nota.ocorrencias}


def _item_padrao(**kw):
    padrao = dict(codigo="ALF001", descricao="Arroz branco tipo 1 5kg",
                  ncm="10063021", qtd="10", vun="22.50")
    padrao.update(kw)
    return _it(padrao.pop("codigo"), padrao.pop("descricao"), padrao.pop("ncm"),
               padrao.pop("qtd"), padrao.pop("vun"), **padrao)


def test_v01_xml_invalido(db, empresa, fonte):
    resumo = _roda(db, empresa, fonte, "quebrado.xml",
                   b'<?xml version="1.0"?>'
                   b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe"><infNFe>x')
    assert resumo.quarentena == 1
    assert resumo.ocorrencias_por_tipo.get("V01") == 1
    assert resumo.notas_novas == 0


def test_v02_dv_da_chave(db, empresa, fonte):
    chave = monta_chave(35, ONTEM.strftime("%y%m"), CNPJ_ALFA, 55, 1, 100, 1, "00000001")
    adulterada = chave[:40] + str((int(chave[40]) + 1) % 10) + chave[41:]
    xml = montar_nota(100, ALFA, [_item_padrao()], ONTEM, chave_forcada=adulterada)
    _roda(db, empresa, fonte, "v02.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V02" in _tipos(nota)


def test_v03_chave_diverge_do_xml(db, empresa, fonte):
    # chave íntegra, mas montada para outro número de nota
    chave_de_outra = monta_chave(35, ONTEM.strftime("%y%m"), CNPJ_ALFA, 55, 1, 999, 1, "00000002")
    xml = montar_nota(101, ALFA, [_item_padrao()], ONTEM, chave_forcada=chave_de_outra)
    _roda(db, empresa, fonte, "v03.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V03" in _tipos(nota)


def test_v04_cnpj_emitente_invalido(db, empresa, fonte):
    xml = montar_nota(102, ("11111111111111", "Emitente Suspeito"),
                      [_item_padrao()], ONTEM)
    _roda(db, empresa, fonte, "v04.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V04" in _tipos(nota)


def test_v05_cnpj_destinatario_invalido(db, empresa, fonte):
    xml = montar_nota(103, ALFA, [_item_padrao()], ONTEM,
                      cnpj_dest="99999999999999")
    _roda(db, empresa, fonte, "v05.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V05" in _tipos(nota)


def test_v06_destinatario_de_outra_empresa(db, empresa, fonte):
    xml = montar_nota(104, ALFA, [_item_padrao()], ONTEM,
                      cnpj_dest="34028316000103")
    _roda(db, empresa, fonte, "v06.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V06" in _tipos(nota)


def test_v07_soma_dos_itens_diverge(db, empresa, fonte):
    xml = montar_nota(105, ALFA, [_item_padrao()], ONTEM,
                      vprod_forcado=D("999.00"), vnf_forcado=D("999.00"))
    _roda(db, empresa, fonte, "v07.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V07" in _tipos(nota)


def test_v08_recomposicao_diverge(db, empresa, fonte):
    xml = montar_nota(106, ALFA, [_item_padrao()], ONTEM, vnf_forcado=D("999.99"))
    _roda(db, empresa, fonte, "v08.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V08" in _tipos(nota)


def test_v09_duplicatas_divergem(db, empresa, fonte):
    xml = montar_nota(107, ALFA, [_item_padrao()], ONTEM,
                      duplicatas=[("001", D("10.00"))])   # total é 225.00
    _roda(db, empresa, fonte, "v09.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "V09" in _tipos(nota)
    assert nota.status != "rejeitada"   # alerta não bloqueia


def test_v10_emissao_no_futuro(db, empresa, fonte):
    amanha = datetime.now(FUSO_SP) + timedelta(days=1)
    xml = montar_nota(108, ALFA, [_item_padrao()], amanha)
    _roda(db, empresa, fonte, "v10.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "rejeitada"
    assert "V10" in _tipos(nota)


def test_v11_emissao_retroativa(db, empresa, fonte):
    antiga = datetime.now(FUSO_SP) - timedelta(days=200)
    xml = montar_nota(109, ALFA, [_item_padrao()], antiga)
    _roda(db, empresa, fonte, "v11.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "V11" in _tipos(nota)
    assert nota.status != "rejeitada"


def test_v12_chave_ja_lancada(db, empresa, fonte):
    xml = montar_nota(110, ALFA, [_item_padrao()], ONTEM)
    _roda(db, empresa, fonte, "primeira.xml", xml)
    resumo = _roda(db, empresa, fonte, "reenvio.xml", xml)
    assert resumo.duplicatas_descartadas == 1
    assert resumo.notas_novas == 0


def test_c01_fornecedor_nao_cadastrado(db, empresa, fonte):
    # emitente com DV válido, mas ausente do cadastro
    from app.utils.documentos import dv_cnpj
    cnpj_novo = "45997418" + "0001" + dv_cnpj("459974180001")
    xml = montar_nota(111, (cnpj_novo, "Fornecedor Desconhecido"),
                      [_item_padrao(codigo="XYZ")], ONTEM)
    _roda(db, empresa, fonte, "c01.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "C01" in _tipos(nota)
    assert nota.fornecedor.ativo is False


def test_c02_item_sem_depara(db, empresa, fonte):
    xml = montar_nota(112, GAMA, [_item_padrao(codigo="GAM-INEXISTENTE")], ONTEM)
    _roda(db, empresa, fonte, "c02.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "C02" in _tipos(nota)


def test_c03_ncm_fora_do_formato(db, empresa, fonte):
    xml = montar_nota(113, ALFA, [_item_padrao(ncm="123")], ONTEM)
    _roda(db, empresa, fonte, "c03.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "C03" in _tipos(nota)
    assert nota.status != "rejeitada"   # informativa


def test_p01_sem_pedido(db, empresa, fonte):
    xml = montar_nota(114, GAMA,
                      [_item_padrao(codigo="GAM-DET500", descricao="Detergente",
                                    ncm="34022000", qtd="10", vun="2.15")], ONTEM)
    _roda(db, empresa, fonte, "p01.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "P01" in _tipos(nota)
    assert nota.status == "aprovada"


def test_p01_bloqueia_quando_parametrizado(db, empresa, fonte):
    parametro = db.query(Parametro).filter_by(empresa_id=empresa.id).one()
    parametro.bloquear_sem_pedido = True
    db.commit()
    xml = montar_nota(115, GAMA,
                      [_item_padrao(codigo="GAM-DET500", descricao="Detergente",
                                    ncm="34022000", qtd="10", vun="2.15")], ONTEM)
    _roda(db, empresa, fonte, "p01b.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "bloqueada"


def test_p02_preco_acima(db, empresa, fonte):
    xml = montar_nota(116, ALFA,
                      [_item_padrao(qtd="50", vun="24.00", xped="PC-1001", nitemped=1)],
                      ONTEM)
    _roda(db, empresa, fonte, "p02.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "bloqueada"
    oc = next(o for o in nota.ocorrencias if o.tipo == "P02")
    assert Decimal(oc.valor_impacto) == Decimal("75.00")   # (24,00-22,50)*50


def test_p03_preco_abaixo(db, empresa, fonte):
    xml = montar_nota(117, ALFA,
                      [_item_padrao(qtd="50", vun="20.00", xped="PC-1001")], ONTEM)
    _roda(db, empresa, fonte, "p03.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "P03" in _tipos(nota)
    assert nota.status == "aprovada"


def test_p04_quantidade_acima(db, empresa, fonte):
    xml = montar_nota(118, ALFA,
                      [_item_padrao(qtd="60", xped="PC-1001")], ONTEM)   # pedido: 50
    _roda(db, empresa, fonte, "p04.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "bloqueada"
    assert "P04" in _tipos(nota)


def test_p05_entrega_parcial(db, empresa, fonte):
    xml = montar_nota(119, ALFA,
                      [_item_padrao(qtd="20", xped="PC-1001")], ONTEM)
    _roda(db, empresa, fonte, "p05.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "P05" in _tipos(nota)
    assert nota.status == "aprovada"


def test_p06_item_fora_do_pedido(db, empresa, fonte):
    xml = montar_nota(120, ALFA, [
        _item_padrao(qtd="50", xped="PC-1001"),
        _it("ALF006", "Macarrao espaguete 500g", "19021900", "10", "3.60",
            xped="PC-1001"),
    ], ONTEM)
    _roda(db, empresa, fonte, "p06.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.status == "bloqueada"
    assert "P06" in _tipos(nota)


def test_p07_item_do_pedido_nao_entregue(db, empresa, fonte):
    xml = montar_nota(121, ALFA,
                      [_item_padrao(qtd="50", xped="PC-1001")], ONTEM)
    _roda(db, empresa, fonte, "p07.xml", xml)
    nota = _unica_nota(db, empresa)
    # feijão e açúcar do PC-1001 não vieram nesta nota
    assert "P07" in _tipos(nota)


def test_p08_frete_acima_do_previsto(db, empresa, fonte):
    xml = montar_nota(122, ALFA,
                      [_item_padrao(qtd="50", xped="PC-1001")], ONTEM,
                      frete=D("300.00"),
                      duplicatas=[("001", D("1425.00"))])
    _roda(db, empresa, fonte, "p08.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "P08" in _tipos(nota)
    assert nota.status == "aprovada"   # alerta não bloqueia


def test_p09_cfop_fora_de_venda(db, empresa, fonte):
    xml = montar_nota(123, ALFA,
                      [_item_padrao(cfop="1102")], ONTEM)
    _roda(db, empresa, fonte, "p09.xml", xml)
    nota = _unica_nota(db, empresa)
    assert "P09" in _tipos(nota)
    assert nota.tipo_operacao == "outro"


def test_devolucao_sem_efeito(db, empresa, fonte):
    from app.models import MovimentoEstoque
    xml = montar_nota(124, ALFA, [_item_padrao(cfop="5202")], ONTEM)
    _roda(db, empresa, fonte, "devolucao.xml", xml)
    nota = _unica_nota(db, empresa)
    assert nota.tipo_operacao == "devolucao"
    assert db.query(MovimentoEstoque).filter_by(empresa_id=empresa.id).count() == 0
