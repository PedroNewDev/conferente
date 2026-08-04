"""Hash de senha, sessão por cookie assinado e resolução do usuário atual."""
from fastapi import Depends, HTTPException, Request, status
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_senha(senha: str) -> str:
    return pwd_context.hash(senha)


def verifica_senha(senha: str, senha_hash: str) -> bool:
    return pwd_context.verify(senha, senha_hash)


def usuario_atual(request: Request, db: Session = Depends(get_db)) -> Usuario:
    """Resolve o usuário logado a partir da sessão. Redireciona ao login se ausente."""
    usuario_id = request.session.get("usuario_id")
    if not usuario_id:
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
            detail="Faça login para continuar.",
        )
    usuario = db.get(Usuario, usuario_id)
    if not usuario or not usuario.ativo:
        request.session.clear()
        raise HTTPException(
            status_code=status.HTTP_303_SEE_OTHER,
            headers={"Location": "/login"},
            detail="Sessão inválida. Faça login novamente.",
        )
    return usuario


def exige_papel(*papeis: str):
    """Dependência que restringe a rota aos papéis informados (admin sempre passa)."""
    def verificador(usuario: Usuario = Depends(usuario_atual)) -> Usuario:
        if usuario.papel != "admin" and usuario.papel not in papeis:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Você não tem permissão para esta ação.",
            )
        return usuario
    return verificador
