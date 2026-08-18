"""Proteção CSRF: token por sessão, gerado para os formulários e
verificado nos POSTs de ação sensível."""
import secrets

from fastapi import Form, HTTPException, Request


def csrf_token(request: Request) -> str:
    """Chamado pelo template: garante um token na sessão e o retorna."""
    token = request.session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        request.session["csrf_token"] = token
    return token


def verifica_csrf(request: Request, csrf_token: str = Form(...)) -> None:
    """Dependência para POSTs: compara o token do formulário com o da sessão."""
    esperado = request.session.get("csrf_token")
    if not esperado or not secrets.compare_digest(csrf_token, esperado):
        raise HTTPException(
            status_code=403,
            detail="Sessão expirada ou formulário inválido. Recarregue a página e tente novamente.",
        )
