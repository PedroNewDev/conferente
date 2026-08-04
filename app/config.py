"""Configurações da aplicação, lidas do arquivo .env com validação."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NOME: str = "Conferente"
    APP_SECRET: str = "troque-esta-chave"
    DATABASE_URL: str = "sqlite:///./conferente.db"

    FONTE_DOCUMENTOS: str = "pasta"  # pasta | imap
    PASTA_ENTRADA: str = "./entrada/novos"
    PASTA_PROCESSADOS: str = "./entrada/processados"
    PASTA_QUARENTENA: str = "./entrada/quarentena"
    PASTA_ARQUIVO: str = "./arquivo"

    IMAP_HOST: str = "imap.gmail.com"
    IMAP_PORTA: int = 993
    IMAP_USUARIO: str = ""
    IMAP_SENHA: str = ""
    IMAP_PASTA: str = "INBOX"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORTA: int = 587
    SMTP_USUARIO: str = ""
    SMTP_SENHA: str = ""
    SMTP_REMETENTE: str = "conferente@exemplo.com.br"

    AGENDADOR_ATIVO: bool = True
    INTERVALO_CICLO_MINUTOS: int = 15


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
