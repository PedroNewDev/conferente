"""Envio do relatório do ciclo por SMTP (biblioteca padrão).

Sem SMTP_USUARIO configurado, o envio é pulado silenciosamente — permite
desenvolver e demonstrar sem depender de rede.
"""
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

from app.config import settings
from app.models import Empresa


def _corpo_resumo(empresa: Empresa, resumo, inicio: datetime) -> str:
    return (
        f"Ciclo de recebimento — {empresa.razao_social}\n"
        f"Início: {inicio.strftime('%d/%m/%Y %H:%M')}\n\n"
        f"Documentos lidos: {resumo.documentos_lidos}\n"
        f"Notas novas: {resumo.notas_novas}\n"
        f"  Aprovadas:  {resumo.aprovadas} (R$ {resumo.valor_aprovado})\n"
        f"  Bloqueadas: {resumo.bloqueadas} (R$ {resumo.valor_bloqueado})\n"
        f"  Rejeitadas: {resumo.rejeitadas}\n"
        f"Duplicatas descartadas: {resumo.duplicatas_descartadas}\n"
        f"Documentos em quarentena: {resumo.quarentena}\n\n"
        f"Impacto financeiro das divergências: R$ {resumo.impacto_divergencias}\n\n"
        f"O relatório completo segue em anexo.\n"
    )


def enviar_relatorio(destinatarios: str, empresa: Empresa, resumo,
                     inicio: datetime, anexo: Path | None) -> bool:
    """Envia o e-mail do ciclo. Devolve True se enviou, False se pulou."""
    if not settings.SMTP_USUARIO:
        return False

    divergencias = resumo.bloqueadas + resumo.rejeitadas
    msg = EmailMessage()
    msg["Subject"] = (f"[Conferente] Ciclo de {inicio.strftime('%d/%m/%Y %H:%M')} — "
                      f"{resumo.notas_novas} notas, {divergencias} divergências")
    msg["From"] = settings.SMTP_REMETENTE
    msg["To"] = [e.strip() for e in destinatarios.split(",") if e.strip()]
    msg.set_content(_corpo_resumo(empresa, resumo, inicio))

    if anexo and anexo.exists():
        subtipo = "pdf" if anexo.suffix == ".pdf" else "html"
        msg.add_attachment(anexo.read_bytes(), maintype="application",
                           subtype=subtipo, filename=anexo.name)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORTA) as smtp:
        smtp.starttls()
        smtp.login(settings.SMTP_USUARIO, settings.SMTP_SENHA)
        smtp.send_message(msg)
    return True
