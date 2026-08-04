"""Criação inicial do esquema a partir dos modelos.

Revision ID: 0001
Revises:
Create Date: 2026-08-04
"""
from alembic import op

from app.database import Base
from app import models  # noqa: F401 — registra as tabelas na Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
