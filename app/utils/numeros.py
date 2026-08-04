"""Aritmética monetária com Decimal. Proibido float em qualquer cálculo."""
from decimal import Decimal, ROUND_HALF_UP

DUAS = Decimal("0.01")
QUATRO = Decimal("0.0001")


def dec(valor, casas=DUAS) -> Decimal:
    if valor is None or valor == "":
        return Decimal("0").quantize(casas)
    return Decimal(str(valor)).quantize(casas, rounding=ROUND_HALF_UP)


def dentro_da_tolerancia(a: Decimal, b: Decimal, tol_abs: Decimal,
                         tol_pct: Decimal = Decimal("0")) -> bool:
    """Aceita se a diferença couber na tolerância absoluta OU na percentual sobre b."""
    diff = abs(a - b)
    if diff <= tol_abs:
        return True
    if b != 0 and tol_pct > 0:
        return (diff / abs(b)) * 100 <= tol_pct
    return False
