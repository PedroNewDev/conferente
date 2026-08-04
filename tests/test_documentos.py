"""Testes de validação de CNPJ."""
from app.utils.documentos import cnpj_valido, dv_cnpj, so_digitos

CNPJS_VALIDOS = [
    "11222333000181",
    "11.444.777/0001-61",
    "34028316000103",   # Correios
    "60701190000104",   # Itaú
]

CNPJS_INVALIDOS = [
    "11222333000180",   # DV errado
    "11111111111111",   # todos iguais
    "123",              # curto demais
]


def test_cnpjs_validos():
    for c in CNPJS_VALIDOS:
        assert cnpj_valido(c), c


def test_cnpjs_invalidos():
    for c in CNPJS_INVALIDOS:
        assert not cnpj_valido(c), c


def test_so_digitos():
    assert so_digitos("11.222.333/0001-81") == "11222333000181"
    assert so_digitos(None) == ""
    assert so_digitos("abc") == ""


def test_dv_cnpj():
    assert dv_cnpj("112223330001") == "81"
