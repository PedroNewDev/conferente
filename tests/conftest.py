"""Fixtures compartilhadas: banco em memória, seed e fonte de pasta temporária."""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import settings
from app.database import Base
from app.fontes.pasta import FontePasta
from app.models import Empresa
from scripts.seed import popular


@pytest.fixture
def db(tmp_path, monkeypatch):
    """Sessão sobre SQLite em memória, com os caminhos de arquivo apontando
    para diretórios temporários."""
    engine = create_engine("sqlite://", poolclass=StaticPool,
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestSession()

    monkeypatch.setattr(settings, "PASTA_ARQUIVO", str(tmp_path / "arquivo"))
    monkeypatch.setattr(settings, "SMTP_USUARIO", "")

    # o relatório é gravado em ./relatorios — redireciona para o tmp
    monkeypatch.chdir(tmp_path)

    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def empresa(db) -> Empresa:
    popular(db)
    return db.query(Empresa).one()


@pytest.fixture
def fonte(tmp_path) -> FontePasta:
    return FontePasta(str(tmp_path / "novos"), str(tmp_path / "processados"),
                      str(tmp_path / "quarentena"))
