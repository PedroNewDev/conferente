"""Data/hora no fuso de negócio da aplicação, independente do fuso do
servidor onde o processo roda (relevante em deploys serverless/containers,
que costumam rodar em UTC)."""
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

FUSO_HORARIO = ZoneInfo("America/Sao_Paulo")


def hoje() -> date:
    """Data corrente no fuso de negócio."""
    return datetime.now(FUSO_HORARIO).date()


def inicio_do_dia_utc(dia: date | None = None) -> datetime:
    """Meia-noite do dia informado (ou hoje) no fuso de negócio, em UTC —
    para comparar com colunas timestamptz armazenadas em UTC."""
    dia = dia or hoje()
    return datetime.combine(dia, time.min, tzinfo=FUSO_HORARIO).astimezone(timezone.utc)
