"""Enums do domínio. Os valores são gravados no banco como texto."""
from enum import Enum


class PapelUsuario(str, Enum):
    ADMIN = "admin"
    COMPRADOR = "comprador"
    FINANCEIRO = "financeiro"


class StatusNota(str, Enum):
    RECEBIDA = "recebida"
    REJEITADA = "rejeitada"
    VALIDADA = "validada"
    APROVADA = "aprovada"
    BLOQUEADA = "bloqueada"
    CANCELADA = "cancelada"


class TipoOperacao(str, Enum):
    COMPRA = "compra"
    DEVOLUCAO = "devolucao"
    REMESSA = "remessa"
    BONIFICACAO = "bonificacao"
    OUTRO = "outro"


class StatusPedido(str, Enum):
    ABERTO = "aberto"
    PARCIAL = "parcial"
    ATENDIDO = "atendido"
    CANCELADO = "cancelado"


class TipoMovimento(str, Enum):
    ENTRADA = "entrada"
    SAIDA = "saida"
    AJUSTE = "ajuste"


class StatusConta(str, Enum):
    ABERTA = "aberta"
    PAGA = "paga"
    CANCELADA = "cancelada"


class Severidade(str, Enum):
    BLOQUEANTE = "bloqueante"
    ALERTA = "alerta"
    INFORMATIVA = "informativa"


class StatusEmail(str, Enum):
    PROCESSADO = "processado"
    QUARENTENA = "quarentena"
    IGNORADO = "ignorado"


class OrigemDocumento(str, Enum):
    PASTA = "pasta"
    IMAP = "imap"
    UPLOAD = "upload"
