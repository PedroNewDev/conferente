"""Gera XMLs de NF-e válidos cobrindo os 15 cenários de teste do projeto.

Usa `monta_chave` do próprio projeto, garantindo coerência entre gerador e
validador. Os CNPJs e pedidos batem com os dados do `scripts/seed.py`.

Uso:
    python scripts/gerar_notas_teste.py --saida ./entrada/novos --cenario todos
"""
import argparse
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.utils.chave_nfe import monta_chave
from app.utils.documentos import dv_cnpj

# Mesmos CNPJs do seed
CNPJ_EMPRESA = "11222333000181"      # destinatário (Mercado Bom Preço)
CNPJ_ALFA = "11444777000161"         # Distribuidora Alfa
CNPJ_BETA = "34028316000103"         # Comercial Beta
CNPJ_GAMA = "60701190000104"         # Indústria Gama
CNPJ_NOVO = "45997418" + "0001" + dv_cnpj("459974180001")   # fornecedor não cadastrado
CNPJ_OUTRO_DEST = "60701190000104"   # destinatário que não é a empresa

FUSO_SP = timezone(timedelta(hours=-3))

D = Decimal


def _fmt(v: Decimal, casas: int = 2) -> str:
    return f"{v:.{casas}f}"


def _item_xml(n: int, codigo: str, descricao: str, ncm: str, cfop: str, unidade: str,
              qtd: Decimal, vun: Decimal, xped: str | None, nitemped: int | None) -> str:
    vprod = (qtd * vun).quantize(D("0.01"))
    ped = ""
    if xped:
        ped = f"<xPed>{xped}</xPed>"
        if nitemped:
            ped += f"<nItemPed>{nitemped}</nItemPed>"
    return f"""<det nItem="{n}"><prod>
<cProd>{codigo}</cProd><cEAN>SEM GTIN</cEAN><xProd>{descricao}</xProd>
<NCM>{ncm}</NCM><CFOP>{cfop}</CFOP><uCom>{unidade}</uCom>
<qCom>{_fmt(qtd, 4)}</qCom><vUnCom>{_fmt(vun, 4)}</vUnCom><vProd>{_fmt(vprod)}</vProd>
{ped}</prod></det>"""


def montar_nota(numero: int, emitente: tuple[str, str], itens: list[dict],
                data_emissao: datetime, cnpj_dest: str = CNPJ_EMPRESA,
                frete: Decimal = D("0"), natureza: str = "VENDA DE MERCADORIA",
                duplicatas: list[tuple[str, Decimal]] | None = None,
                inf_cpl: str | None = None, vnf_forcado: Decimal | None = None,
                vprod_forcado: Decimal | None = None,
                chave_forcada: str | None = None) -> bytes:
    """Monta o XML completo (nfeProc) de uma nota. itens: dicts com as chaves
    codigo, descricao, ncm, cfop, unidade, qtd, vun, xped, nitemped."""
    cnpj_emit, nome_emit = emitente
    aamm = data_emissao.strftime("%y%m")
    chave = chave_forcada or monta_chave(35, aamm, cnpj_emit, 55, 1, numero, 1,
                                         f"{numero * 7 % 100000000:08d}")

    vprod_total = vprod_forcado if vprod_forcado is not None else \
        sum((i["qtd"] * i["vun"]).quantize(D("0.01")) for i in itens)
    vnf = vnf_forcado if vnf_forcado is not None else (vprod_total + frete)

    dets = "\n".join(
        _item_xml(n + 1, i["codigo"], i["descricao"], i["ncm"], i["cfop"], i["unidade"],
                  i["qtd"], i["vun"], i.get("xped"), i.get("nitemped"))
        for n, i in enumerate(itens)
    )

    cobr = ""
    if duplicatas:
        dups = "".join(
            f"<dup><nDup>{n}</nDup><dVenc>{(data_emissao + timedelta(days=30 * (idx + 1))).date().isoformat()}</dVenc>"
            f"<vDup>{_fmt(v)}</vDup></dup>"
            for idx, (n, v) in enumerate(duplicatas)
        )
        cobr = f"<cobr>{dups}</cobr>"

    inf_adic = f"<infAdic><infCpl>{inf_cpl}</infCpl></infAdic>" if inf_cpl else ""

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc xmlns="http://www.portalfiscal.inf.br/nfe" versao="4.00">
<NFe><infNFe Id="NFe{chave}" versao="4.00">
<ide><cUF>35</cUF><natOp>{natureza}</natOp><mod>55</mod><serie>1</serie>
<nNF>{numero}</nNF><dhEmi>{data_emissao.isoformat()}</dhEmi><tpNF>1</tpNF></ide>
<emit><CNPJ>{cnpj_emit}</CNPJ><xNome>{nome_emit}</xNome>
<enderEmit><xMun>Sao Paulo</xMun><UF>SP</UF></enderEmit></emit>
<dest><CNPJ>{cnpj_dest}</CNPJ><xNome>Mercado Bom Preco LTDA</xNome></dest>
{dets}
<total><ICMSTot><vProd>{_fmt(vprod_total)}</vProd><vDesc>0.00</vDesc>
<vFrete>{_fmt(frete)}</vFrete><vSeg>0.00</vSeg><vOutro>0.00</vOutro>
<vIPI>0.00</vIPI><vST>0.00</vST><vNF>{_fmt(vnf)}</vNF></ICMSTot></total>
{cobr}
{inf_adic}
</infNFe></NFe>
<protNFe versao="4.00"><infProt><nProt>135{datetime.now().year}0000000001</nProt>
<cStat>100</cStat></infProt></protNFe>
</nfeProc>"""
    return xml.encode("utf-8")


def _it(codigo, descricao, ncm, qtd, vun, unidade="FD", cfop="5102",
        xped=None, nitemped=None) -> dict:
    return {"codigo": codigo, "descricao": descricao, "ncm": ncm, "cfop": cfop,
            "unidade": unidade, "qtd": D(qtd), "vun": D(vun),
            "xped": xped, "nitemped": nitemped}


def gerar_todos(saida: Path) -> list[str]:
    saida.mkdir(parents=True, exist_ok=True)
    ontem = (datetime.now(FUSO_SP) - timedelta(days=1)).replace(microsecond=0)
    alfa = (CNPJ_ALFA, "Distribuidora Alfa de Alimentos LTDA")
    beta = (CNPJ_BETA, "Comercial Beta Distribuicao SA")
    gama = (CNPJ_GAMA, "Industria Gama de Produtos de Limpeza LTDA")
    gerados: list[str] = []

    def escreve(nome: str, conteudo: bytes) -> None:
        (saida / nome).write_bytes(conteudo)
        gerados.append(nome)

    # 01 — bate exatamente com o pedido PC-1001 (Alfa)
    vnf_01 = D("2313.00") + D("120.00")
    nota01 = montar_nota(90001, alfa, [
        _it("ALF001", "Arroz branco tipo 1 5kg", "10063021", "50", "22.50", xped="PC-1001", nitemped=1),
        _it("ALF002", "Feijao carioca 1kg", "07133399", "80", "7.80", xped="PC-1001", nitemped=2),
        _it("ALF003", "Acucar cristal 2kg", "17019900", "60", "9.40", xped="PC-1001", nitemped=3),
    ], ontem, frete=D("120.00"),
        duplicatas=[("001", vnf_01 / 2), ("002", vnf_01 / 2)])
    escreve("01_nota_perfeita.xml", nota01)

    # 02 — preço 8% acima no óleo (pedido PC-1002)
    escreve("02_preco_acima.xml", montar_nota(90002, alfa, [
        _it("ALF004", "Oleo de soja 900ml", "15071000", "100", "7.45", unidade="CX", xped="PC-1002"),
        _it("ALF005", "Cafe torrado e moido 500g", "09012100", "40", "14.20", unidade="CX", xped="PC-1002"),
    ], ontem, duplicatas=[("001", D("1313.00"))]))

    # 03 — quantidade acima do saldo do pedido PC-1003 (Beta)
    escreve("03_quantidade_acima.xml", montar_nota(90003, beta, [
        _it("BET001", "Leite integral UHT 1L", "04012010", "150", "4.85", unidade="CX", xped="PC-1003"),
    ], ontem, duplicatas=[("001", D("727.50"))]))

    # 04 — item extra que não consta do pedido PC-1004 (Beta)
    escreve("04_item_nao_pedido.xml", montar_nota(90004, beta, [
        _it("BET005", "Biscoito cream cracker 400g", "19053100", "60", "4.10", unidade="CX", xped="PC-1004"),
        _it("BET006", "Detergente neutro 500ml", "34022000", "90", "2.15", unidade="CX", xped="PC-1004"),
        _it("BET003", "Sal refinado 1kg", "25010020", "20", "1.95", xped="PC-1004"),
    ], ontem, duplicatas=[("001", D("478.50"))]))

    # 05 — entrega parcial (metade) do pedido PC-1004
    escreve("05_entrega_parcial.xml", montar_nota(90005, beta, [
        _it("BET005", "Biscoito cream cracker 400g", "19053100", "30", "4.10", unidade="CX", xped="PC-1004"),
        _it("BET006", "Detergente neutro 500ml", "34022000", "45", "2.15", unidade="CX", xped="PC-1004"),
    ], ontem, duplicatas=[("001", D("219.75"))]))

    # 06 — cópia idêntica da nota 01 (mesma chave)
    escreve("06_duplicada.xml", nota01)

    # 07 — um dígito da chave trocado (DV deixa de bater)
    chave_boa = monta_chave(35, ontem.strftime("%y%m"), CNPJ_ALFA, 55, 1, 90007,
                            1, f"{90007 * 7 % 100000000:08d}")
    pos = 40   # dígito dentro do código numérico: não afeta V03
    trocado = str((int(chave_boa[pos]) + 1) % 10)
    chave_ruim = chave_boa[:pos] + trocado + chave_boa[pos + 1:]
    escreve("07_chave_adulterada.xml", montar_nota(90007, alfa, [
        _it("ALF001", "Arroz branco tipo 1 5kg", "10063021", "10", "22.50"),
    ], ontem, duplicatas=[("001", D("225.00"))], chave_forcada=chave_ruim))

    # 08 — vNF não bate com a recomposição dos totais
    escreve("08_soma_divergente.xml", montar_nota(90008, alfa, [
        _it("ALF001", "Arroz branco tipo 1 5kg", "10063021", "10", "22.50"),
    ], ontem, vnf_forcado=D("999.99"), duplicatas=[("001", D("999.99"))]))

    # 09 — destinatário que não é a empresa
    escreve("09_outro_destinatario.xml", montar_nota(90009, alfa, [
        _it("ALF001", "Arroz branco tipo 1 5kg", "10063021", "10", "22.50"),
    ], ontem, cnpj_dest=CNPJ_OUTRO_DEST, duplicatas=[("001", D("225.00"))]))

    # 10 — emitente não cadastrado (fornecedor novo)
    escreve("10_fornecedor_novo.xml", montar_nota(90010, (CNPJ_NOVO, "Atacadao Delta LTDA"), [
        _it("DEL001", "Papel toalha institucional", "48181000", "25", "8.90", unidade="CX"),
    ], ontem, duplicatas=[("001", D("222.50"))]))

    # 11 — fornecedor conhecido (Gama), sem pedido em aberto
    escreve("11_sem_pedido.xml", montar_nota(90011, gama, [
        _it("GAM-DET500", "Detergente neutro Gama 500ml", "34022000", "50", "2.10", unidade="CX"),
    ], ontem, duplicatas=[("001", D("105.00"))]))

    # 12 — devolução (CFOP 5202), sem efeito no estoque
    escreve("12_devolucao.xml", montar_nota(90012, alfa, [
        _it("ALF001", "Arroz branco tipo 1 5kg", "10063021", "5", "22.50", cfop="5202"),
    ], ontem, natureza="DEVOLUCAO DE COMPRA", duplicatas=[("001", D("112.50"))]))

    # 13 — XML corrompido (malformado de propósito)
    escreve("13_xml_corrompido.xml",
            b"<?xml version='1.0'?>"
            b"<nfeProc xmlns=\"http://www.portalfiscal.inf.br/nfe\">"
            b"<NFe><infNFe>quebrado")

    # 14 — sem bloco cobr: conta única com vencimento arbitrado
    escreve("14_sem_duplicatas.xml", montar_nota(90014, alfa, [
        _it("ALF004", "Oleo de soja 900ml", "15071000", "100", "6.90", unidade="CX", xped="PC-1002"),
        _it("ALF005", "Cafe torrado e moido 500g", "09012100", "40", "14.20", unidade="CX", xped="PC-1002"),
    ], ontem))

    # 15 — código do fornecedor sem de-para
    escreve("15_produto_sem_depara.xml", montar_nota(90015, gama, [
        _it("GAM-XYZ", "Sabao em barra Gama 5un", "34011190", "10", "5.00", unidade="CX"),
    ], ontem, duplicatas=[("001", D("50.00"))]))

    return gerados


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera XMLs de NF-e para os cenários de teste.")
    parser.add_argument("--saida", default="./entrada/novos")
    parser.add_argument("--cenario", default="todos")
    args = parser.parse_args()
    gerados = gerar_todos(Path(args.saida))
    print(f"{len(gerados)} arquivos gerados em {args.saida}:")
    for g in gerados:
        print(f"  {g}")


if __name__ == "__main__":
    main()
