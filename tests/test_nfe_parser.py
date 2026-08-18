"""Testes do parser de NF-e sobre XMLs gerados pelo próprio projeto."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.nfe_parser import NFeParseError, parse_nfe
from scripts.gerar_notas_teste import CNPJ_ALFA, CNPJ_EMPRESA, D, _it, montar_nota

ONTEM = (datetime.now(timezone(timedelta(hours=-3))) - timedelta(days=1)).replace(microsecond=0)


def _nota_padrao(**kwargs) -> bytes:
    padrao = dict(
        numero=1234,
        emitente=(CNPJ_ALFA, "Distribuidora Alfa de Alimentos LTDA"),
        itens=[
            _it("ALF001", "Arroz branco tipo 1 5kg", "10063021", "50", "22.50",
                xped="PC-1001", nitemped=1),
            _it("ALF002", "Feijao carioca 1kg", "07133399", "80", "7.80"),
        ],
        data_emissao=ONTEM,
        frete=D("120.00"),
        duplicatas=[("001", D("922.50")), ("002", D("946.50"))],
    )
    padrao.update(kwargs)
    return montar_nota(**padrao)


def test_extracao_completa():
    nota = parse_nfe(_nota_padrao())
    assert len(nota.chave) == 44
    assert nota.numero == 1234
    assert nota.serie == 1
    assert nota.modelo == "55"
    assert nota.cnpj_emitente == CNPJ_ALFA
    assert nota.cnpj_destinatario == CNPJ_EMPRESA
    assert nota.data_emissao.tzinfo is not None

    assert len(nota.itens) == 2
    item = nota.itens[0]
    assert item.n_item == 1
    assert item.codigo == "ALF001"
    assert item.quantidade == Decimal("50.0000")
    assert item.valor_unitario == Decimal("22.5000")
    assert item.valor_total == Decimal("1125.00")
    assert item.numero_pedido == "PC-1001"
    assert item.item_pedido == 1
    assert item.ean is None  # "SEM GTIN" vira None

    assert nota.valor_produtos == Decimal("1749.00")
    assert nota.valor_frete == Decimal("120.00")
    assert nota.valor_total == Decimal("1869.00")

    assert len(nota.duplicatas) == 2
    assert nota.duplicatas[0].valor == Decimal("922.50")
    assert nota.protocolo is not None


def test_nota_sem_cobr():
    nota = parse_nfe(_nota_padrao(duplicatas=None))
    assert nota.duplicatas == []


def test_raiz_nfe_sem_protocolo():
    xml = _nota_padrao()
    # extrai só o <NFe>...</NFe> de dentro do nfeProc
    inicio = xml.index(b"<NFe>")
    fim = xml.index(b"</NFe>") + len(b"</NFe>")
    corpo = (b'<?xml version="1.0" encoding="UTF-8"?>'
             b'<NFe xmlns="http://www.portalfiscal.inf.br/nfe">'
             + xml[inicio + len(b"<NFe>"):fim - len(b"</NFe>")] + b"</NFe>")
    nota = parse_nfe(corpo)
    assert nota.numero == 1234
    assert nota.protocolo is None


def test_xml_malformado():
    with pytest.raises(NFeParseError):
        parse_nfe(b"<?xml version='1.0'?><nfeProc><NFe>quebrado")


def test_raiz_inesperada():
    with pytest.raises(NFeParseError):
        parse_nfe(b"<?xml version='1.0'?><outra/>")


def test_entidade_xml_nao_e_expandida():
    """XML com DOCTYPE declarando entidades (ataque XXE / "billion laughs")
    não deve ter a entidade expandida — o parser deve ignorá-la ou falhar,
    nunca substituir o conteúdo."""
    payload = (b'<?xml version="1.0"?>'
              b'<!DOCTYPE nfeProc [<!ENTITY bomba "AAAAAAAAAAAAAAAAAAAA">]>'
              b'<nfeProc>&bomba;</nfeProc>')
    with pytest.raises(NFeParseError):
        parse_nfe(payload)


def test_pedido_em_infcpl():
    nota = parse_nfe(_nota_padrao(inf_cpl="Ref. PEDIDO PC-1001. Entrega em 5 dias."))
    assert nota.numero_pedido_infcpl() == "PC-1001"

    nota2 = parse_nfe(_nota_padrao(inf_cpl="OC 4567"))
    assert nota2.numero_pedido_infcpl() == "4567"

    nota3 = parse_nfe(_nota_padrao(inf_cpl="Sem referencia"))
    assert nota3.numero_pedido_infcpl() is None
