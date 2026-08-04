"""Validação de CNPJ/CPF. Algoritmo validado previamente — não alterar."""


def dv_cnpj(base12: str) -> str:
    def calc(nums, pesos):
        s = sum(int(n) * p for n, p in zip(nums, pesos))
        r = s % 11
        return "0" if r < 2 else str(11 - r)
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = calc(base12, p1)
    return d1 + calc(base12 + d1, p2)


def so_digitos(valor: str) -> str:
    return "".join(c for c in (valor or "") if c.isdigit())


def cnpj_valido(cnpj: str) -> bool:
    d = so_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    return dv_cnpj(d[:12]) == d[12:]
