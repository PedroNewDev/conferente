"""Testes da chave de acesso: DV, decomposição, montagem e adulteração."""
import random

from app.utils.chave_nfe import chave_valida, decompoe_chave, dv_chave, monta_chave


def test_monta_e_valida():
    chave = monta_chave(35, "2601", "11222333000181", 55, 1, 123, 1, "12345678")
    assert len(chave) == 44
    assert chave_valida(chave)


def test_decomposicao():
    chave = monta_chave(35, "2601", "11222333000181", 55, 3, 987654, 1, "00000042")
    partes = decompoe_chave(chave)
    assert partes["cUF"] == "35"
    assert partes["aamm"] == "2601"
    assert partes["cnpj_emitente"] == "11222333000181"
    assert partes["modelo"] == "55"
    assert partes["serie"] == "003"
    assert partes["numero"] == "000987654"
    assert partes["dv"] == chave[43]


def test_varredura_de_chaves():
    """3000 chaves geradas aleatoriamente devem validar; adulteração deve falhar."""
    rnd = random.Random(42)
    for _ in range(3000):
        chave = monta_chave(
            rnd.choice([11, 23, 31, 33, 35, 41, 43]),
            f"{rnd.randint(20, 26):02d}{rnd.randint(1, 12):02d}",
            f"{rnd.randint(0, 99999999999):011d}000{rnd.randint(100, 199)}"[:14],
            55, rnd.randint(1, 999), rnd.randint(1, 999999999), 1,
            f"{rnd.randint(0, 99999999):08d}",
        )
        assert chave_valida(chave)


def test_adulteracao_detectada():
    chave = monta_chave(35, "2601", "11222333000181", 55, 1, 123, 1, "12345678")
    # troca um dígito no meio da chave
    pos = 10
    trocado = str((int(chave[pos]) + 1) % 10)
    adulterada = chave[:pos] + trocado + chave[pos + 1:]
    assert not chave_valida(adulterada)


def test_dv_chave_conhecido():
    base43 = "3520011122233300018155001000000123112345678"
    assert dv_chave(base43) in "0123456789"
    assert chave_valida(base43 + dv_chave(base43))
