"""Adaptador para execução serverless (Vercel) — ambiente de demonstração.

Serverless não tem disco persistente: o banco vive em /tmp e é recriado e
semeado no primeiro acesso de cada instância, já com os 15 XMLs de teste na
pasta de entrada. Cada visitante recebe, portanto, um ambiente limpo.

O ambiente oficial de execução continua sendo o `docker-compose.yml`
(PostgreSQL, agendador ativo, disco persistente).
"""
import os
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

TRABALHO = Path("/tmp/conferente")

# Configuração precisa existir antes de importar qualquer módulo do app,
# porque app.config lê o ambiente na importação.
os.environ.setdefault("APP_SECRET", "demonstracao-conferente-vercel")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TRABALHO}/conferente.db")
os.environ.setdefault("AGENDADOR_ATIVO", "false")   # sem processo de fundo em serverless
os.environ.setdefault("FONTE_DOCUMENTOS", "pasta")
os.environ.setdefault("PASTA_ENTRADA", f"{TRABALHO}/entrada/novos")
os.environ.setdefault("PASTA_PROCESSADOS", f"{TRABALHO}/entrada/processados")
os.environ.setdefault("PASTA_QUARENTENA", f"{TRABALHO}/entrada/quarentena")
os.environ.setdefault("PASTA_ARQUIVO", f"{TRABALHO}/arquivo")
os.environ.setdefault("PASTA_RELATORIOS", f"{TRABALHO}/relatorios")

TRABALHO.mkdir(parents=True, exist_ok=True)

from app.database import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from scripts.gerar_notas_teste import gerar_todos  # noqa: E402
from scripts.seed import popular  # noqa: E402


def preparar_demonstracao() -> None:
    """Cria o esquema, semeia os dados e gera os XMLs de teste — uma vez por
    instância. Falha aqui não pode derrubar a função: o app sobe mesmo assim."""
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if popular(db):
            gerar_todos(Path(os.environ["PASTA_ENTRADA"]))
    finally:
        db.close()


try:
    preparar_demonstracao()
except Exception as exc:  # noqa: BLE001 — ambiente de demonstração
    print(f"[demonstracao] falha ao preparar dados iniciais: {exc}")

# A Vercel procura por `app` (ASGI) neste módulo.
