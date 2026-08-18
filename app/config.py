"""Configurações da aplicação, lidas do arquivo .env com validação."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    APP_NOME: str = "Conferente"
    APP_SECRET: str = "troque-esta-chave"
    AMBIENTE: str = "desenvolvimento"  # desenvolvimento | producao
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

    # Demonstração: entra automaticamente como administrador, sem tela de
    # login. A autenticação continua implementada e a tela segue disponível
    # em /login para trocar de papel. NUNCA ligar em produção real.
    ACESSO_LIVRE: bool = False


@lru_cache
def get_settings() -> Settings:
    config = Settings()
    if config.AMBIENTE == "producao" and config.APP_SECRET == "troque-esta-chave":
        raise RuntimeError(
            "APP_SECRET não foi alterado do valor padrão. "
            "Defina uma chave própria antes de iniciar em produção."
        )
    return config


settings = get_settings()
