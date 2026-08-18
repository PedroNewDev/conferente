"""Conversão de campos de formulário com erro amigável em vez de 500."""
from datetime import date
from decimal import Decimal, InvalidOperation


class ErroFormulario(Exception):
    """Entrada do usuário inválida — a rota deve capturar e redirecionar
    de volta ao formulário com a mensagem em `erro`."""


def decimal_do_form(valor: str, campo: str) -> Decimal:
    try:
        return Decimal(valor)
    except InvalidOperation:
        raise ErroFormulario(f"Valor inválido para {campo}: '{valor}'.")


def data_do_form(valor: str, campo: str) -> date:
    try:
        return date.fromisoformat(valor)
    except ValueError:
        raise ErroFormulario(f"Data inválida para {campo}: '{valor}'.")
