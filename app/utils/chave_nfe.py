"""Chave de acesso da NF-e: 44 dígitos.

Composição: cUF(2) + AAMM(4) + CNPJ(14) + modelo(2) + série(3) + número(9)
+ tpEmis(1) + código numérico(8) + DV(1).

Algoritmo validado previamente — não alterar.
"""
from app.utils.documentos import so_digitos


def dv_chave(base43: str) -> str:
    """Módulo 11, pesos cíclicos 2..9 da direita para a esquerda."""
    peso, soma = 2, 0
    for c in reversed(base43):
        soma += int(c) * peso
        peso = 2 if peso == 9 else peso + 1
    resto = soma % 11
    return "0" if resto in (0, 1) else str(11 - resto)


def chave_valida(chave: str) -> bool:
    d = so_digitos(chave)
    return len(d) == 44 and dv_chave(d[:43]) == d[43]


def decompoe_chave(chave: str) -> dict:
    d = so_digitos(chave)
    return {"cUF": d[0:2], "aamm": d[2:6], "cnpj_emitente": d[6:20],
            "modelo": d[20:22], "serie": d[22:25], "numero": d[25:34],
            "tp_emis": d[34:35], "codigo_numerico": d[35:43], "dv": d[43:44]}


def monta_chave(c_uf, aamm, cnpj, modelo, serie, numero, tp_emis, codigo_numerico) -> str:
    base = (f"{int(c_uf):02d}{aamm}{so_digitos(cnpj).zfill(14)}{int(modelo):02d}"
            f"{int(serie):03d}{int(numero):09d}{int(tp_emis):01d}{codigo_numerico.zfill(8)}")
    assert len(base) == 43
    return base + dv_chave(base)
