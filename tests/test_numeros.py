"""Testes de aritmética Decimal e tolerância."""
from decimal import Decimal

from app.utils.numeros import DUAS, QUATRO, dec, dentro_da_tolerancia


def test_dec_arredonda_meio_para_cima():
    assert dec("1.005") == Decimal("1.01")
    assert dec("1.004") == Decimal("1.00")


def test_dec_vazio_e_none():
    assert dec(None) == Decimal("0.00")
    assert dec("") == Decimal("0.00")


def test_dec_quatro_casas():
    assert dec("1.23456", QUATRO) == Decimal("1.2346")


def test_tolerancia_absoluta():
    assert dentro_da_tolerancia(Decimal("100.04"), Decimal("100.00"), Decimal("0.05"))
    assert not dentro_da_tolerancia(Decimal("100.06"), Decimal("100.00"), Decimal("0.05"))


def test_tolerancia_percentual():
    # 0,4% de diferença com tolerância de 0,5%
    assert dentro_da_tolerancia(Decimal("100.40"), Decimal("100.00"),
                                Decimal("0.05"), Decimal("0.50"))
    # 0,6% de diferença estoura a tolerância de 0,5%
    assert not dentro_da_tolerancia(Decimal("100.60"), Decimal("100.00"),
                                    Decimal("0.05"), Decimal("0.50"))


def test_tolerancia_base_zero():
    assert dentro_da_tolerancia(Decimal("0.03"), Decimal("0"), Decimal("0.05"))
    assert not dentro_da_tolerancia(Decimal("1.00"), Decimal("0"), Decimal("0.05"), Decimal("10"))
