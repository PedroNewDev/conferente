"""Busca de registros sempre filtrada por empresa — evita repetir o filtro
manualmente em cada router e esquecer de vincular por empresa em algum POST."""
from typing import TypeVar

from fastapi import HTTPException
from sqlalchemy.orm import Session

Modelo = TypeVar("Modelo")


def obtem_ou_404(db: Session, modelo: type[Modelo], id_: int, empresa_id: int,
                  mensagem: str = "Registro não encontrado.") -> Modelo:
    """Busca `modelo` por id, restrito à empresa do usuário; 404 se não achar
    ou pertencer a outra empresa."""
    obj = db.query(modelo).filter_by(id=id_, empresa_id=empresa_id).first()
    if not obj:
        raise HTTPException(404, mensagem)
    return obj
