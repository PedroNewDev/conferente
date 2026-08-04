"""Recursos compartilhados pelos routers: templates e filtros de exibição."""
from decimal import Decimal
from pathlib import Path

from fastapi.templating import Jinja2Templates

from app.config import settings

# Caminho absoluto: o processo pode ser iniciado de qualquer diretório
TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES))


def moeda(valor) -> str:
    """Formata em real brasileiro: 1234.5 -> 1.234,50"""
    if valor is None:
        return "—"
    v = Decimal(str(valor)).quantize(Decimal("0.01"))
    inteiro, _, decimal = f"{v:.2f}".partition(".")
    negativo = inteiro.startswith("-")
    inteiro = inteiro.lstrip("-")
    partes = []
    while len(inteiro) > 3:
        partes.insert(0, inteiro[-3:])
        inteiro = inteiro[:-3]
    partes.insert(0, inteiro)
    return ("-" if negativo else "") + ".".join(partes) + "," + decimal


def quantidade(valor) -> str:
    """Quantidade sem zeros inúteis: 50.0000 -> 50 · 2.5000 -> 2,5"""
    if valor is None:
        return "—"
    v = Decimal(str(valor)).normalize()
    texto = format(v, "f").replace(".", ",")
    return texto


def data_br(valor) -> str:
    if valor is None:
        return "—"
    return valor.strftime("%d/%m/%Y")


def data_hora_br(valor) -> str:
    if valor is None:
        return "—"
    return valor.strftime("%d/%m/%Y %H:%M")


def cnpj_fmt(valor: str | None) -> str:
    if not valor or len(valor) != 14:
        return valor or "—"
    return f"{valor[:2]}.{valor[2:5]}.{valor[5:8]}/{valor[8:12]}-{valor[12:]}"


templates.env.filters["moeda"] = moeda
templates.env.filters["qtd"] = quantidade
templates.env.filters["data_br"] = data_br
templates.env.filters["data_hora_br"] = data_hora_br
templates.env.filters["cnpj"] = cnpj_fmt

templates.env.globals["acesso_livre"] = settings.ACESSO_LIVRE

ROTULOS_STATUS_NOTA = {
    "recebida": "Recebida", "rejeitada": "Rejeitada", "validada": "Validada",
    "aprovada": "Aprovada", "bloqueada": "Bloqueada", "cancelada": "Cancelada",
}
templates.env.globals["rotulo_status"] = lambda s: ROTULOS_STATUS_NOTA.get(s, s)
