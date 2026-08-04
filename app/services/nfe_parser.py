"""Parser de NF-e: XML -> dataclasses.

Aceita raiz `nfeProc` (nota autorizada, com protocolo) ou `NFe` (sem protocolo).
O parser não valida nada — apenas extrai. Erros de estrutura levantam
`NFeParseError`, que o pipeline captura para gerar a ocorrência V01.
"""
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from lxml import etree

from app.utils.numeros import QUATRO, dec

NS = {"nfe": "http://www.portalfiscal.inf.br/nfe"}

# Padrões aceitos em infCpl para identificar o pedido: PEDIDO 1234, PED. 1234, OC 1234
PADRAO_PEDIDO_INFCPL = re.compile(r"\b(?:PEDIDO|PED\.?|OC)\s*[:\-]?\s*([A-Za-z0-9\-\/]+)",
                                  re.IGNORECASE)


class NFeParseError(Exception):
    """XML não pôde ser interpretado como NF-e."""


@dataclass
class ItemNFe:
    n_item: int
    codigo: str
    ean: str | None
    descricao: str
    ncm: str | None
    cfop: str
    unidade: str
    quantidade: Decimal
    valor_unitario: Decimal
    valor_total: Decimal
    numero_pedido: str | None
    item_pedido: int | None


@dataclass
class DuplicataNFe:
    numero: str | None
    vencimento: date
    valor: Decimal


@dataclass
class NotaFiscalNFe:
    chave: str
    numero: int
    serie: int
    modelo: str
    data_emissao: datetime
    natureza_operacao: str
    tipo_nf: str
    cnpj_emitente: str
    nome_emitente: str
    uf_emitente: str | None
    municipio_emitente: str | None
    cnpj_destinatario: str | None
    nome_destinatario: str | None
    itens: list[ItemNFe]
    duplicatas: list[DuplicataNFe]
    valor_produtos: Decimal
    valor_desconto: Decimal
    valor_frete: Decimal
    valor_seguro: Decimal
    valor_outros: Decimal
    valor_ipi: Decimal
    valor_st: Decimal
    valor_total: Decimal
    informacoes_complementares: str | None
    protocolo: str | None
    codigo_status: str | None

    def numero_pedido_infcpl(self) -> str | None:
        """Extrai um candidato a número de pedido das informações complementares."""
        if not self.informacoes_complementares:
            return None
        m = PADRAO_PEDIDO_INFCPL.search(self.informacoes_complementares)
        return m.group(1) if m else None


def _texto(no, caminho: str) -> str | None:
    if no is None:
        return None
    achado = no.find(caminho, NS)
    if achado is None or achado.text is None:
        return None
    return achado.text.strip() or None


def parse_nfe(conteudo: bytes) -> NotaFiscalNFe:
    """Interpreta o XML de uma NF-e e devolve a estrutura extraída."""
    try:
        raiz = etree.fromstring(conteudo)
    except etree.XMLSyntaxError as exc:
        raise NFeParseError(f"XML malformado: {exc}") from exc

    tag = etree.QName(raiz).localname
    if tag == "nfeProc":
        nfe = raiz.find("nfe:NFe", NS)
        prot = raiz.find("nfe:protNFe/nfe:infProt", NS)
    elif tag == "NFe":
        nfe = raiz
        prot = None
    else:
        raise NFeParseError(f"Raiz inesperada: {tag} — não é uma NF-e.")

    if nfe is None:
        raise NFeParseError("Elemento NFe ausente no nfeProc.")

    inf = nfe.find("nfe:infNFe", NS)
    if inf is None:
        raise NFeParseError("Elemento infNFe ausente.")

    chave = (inf.get("Id") or "").removeprefix("NFe")
    if not chave:
        raise NFeParseError("Atributo Id da infNFe ausente.")

    ide = inf.find("nfe:ide", NS)
    emit = inf.find("nfe:emit", NS)
    dest = inf.find("nfe:dest", NS)
    total = inf.find("nfe:total/nfe:ICMSTot", NS)
    if ide is None or emit is None or total is None:
        raise NFeParseError("Blocos obrigatórios (ide/emit/total) ausentes.")

    dh_emi = _texto(ide, "nfe:dhEmi")
    if not dh_emi:
        raise NFeParseError("Data de emissão (dhEmi) ausente.")
    try:
        data_emissao = datetime.fromisoformat(dh_emi)
    except ValueError as exc:
        raise NFeParseError(f"Data de emissão inválida: {dh_emi}") from exc

    itens: list[ItemNFe] = []
    for det in inf.findall("nfe:det", NS):
        prod = det.find("nfe:prod", NS)
        if prod is None:
            raise NFeParseError(f"det sem prod (nItem={det.get('nItem')}).")
        ean = _texto(prod, "nfe:cEAN")
        if ean and ean.upper() == "SEM GTIN":
            ean = None
        item_pedido = _texto(prod, "nfe:nItemPed")
        itens.append(ItemNFe(
            n_item=int(det.get("nItem", "0")),
            codigo=_texto(prod, "nfe:cProd") or "",
            ean=ean,
            descricao=_texto(prod, "nfe:xProd") or "",
            ncm=_texto(prod, "nfe:NCM"),
            cfop=_texto(prod, "nfe:CFOP") or "",
            unidade=_texto(prod, "nfe:uCom") or "",
            quantidade=dec(_texto(prod, "nfe:qCom"), QUATRO),
            valor_unitario=dec(_texto(prod, "nfe:vUnCom"), QUATRO),
            valor_total=dec(_texto(prod, "nfe:vProd")),
            numero_pedido=_texto(prod, "nfe:xPed"),
            item_pedido=int(item_pedido) if item_pedido else None,
        ))

    duplicatas: list[DuplicataNFe] = []
    for dup in inf.findall("nfe:cobr/nfe:dup", NS):
        venc = _texto(dup, "nfe:dVenc")
        if not venc:
            continue
        duplicatas.append(DuplicataNFe(
            numero=_texto(dup, "nfe:nDup"),
            vencimento=date.fromisoformat(venc),
            valor=dec(_texto(dup, "nfe:vDup")),
        ))

    return NotaFiscalNFe(
        chave=chave,
        numero=int(_texto(ide, "nfe:nNF") or 0),
        serie=int(_texto(ide, "nfe:serie") or 0),
        modelo=_texto(ide, "nfe:mod") or "",
        data_emissao=data_emissao,
        natureza_operacao=_texto(ide, "nfe:natOp") or "",
        tipo_nf=_texto(ide, "nfe:tpNF") or "",
        cnpj_emitente=_texto(emit, "nfe:CNPJ") or "",
        nome_emitente=_texto(emit, "nfe:xNome") or "",
        uf_emitente=_texto(emit, "nfe:enderEmit/nfe:UF"),
        municipio_emitente=_texto(emit, "nfe:enderEmit/nfe:xMun"),
        cnpj_destinatario=_texto(dest, "nfe:CNPJ") or _texto(dest, "nfe:CPF"),
        nome_destinatario=_texto(dest, "nfe:xNome"),
        itens=itens,
        duplicatas=duplicatas,
        valor_produtos=dec(_texto(total, "nfe:vProd")),
        valor_desconto=dec(_texto(total, "nfe:vDesc")),
        valor_frete=dec(_texto(total, "nfe:vFrete")),
        valor_seguro=dec(_texto(total, "nfe:vSeg")),
        valor_outros=dec(_texto(total, "nfe:vOutro")),
        valor_ipi=dec(_texto(total, "nfe:vIPI")),
        valor_st=dec(_texto(total, "nfe:vST")),
        valor_total=dec(_texto(total, "nfe:vNF")),
        informacoes_complementares=_texto(inf, "nfe:infAdic/nfe:infCpl"),
        protocolo=_texto(prot, "nfe:nProt") if prot is not None else None,
        codigo_status=_texto(prot, "nfe:cStat") if prot is not None else None,
    )
