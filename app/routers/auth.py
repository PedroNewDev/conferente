"""Autenticação: login, logout."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.models import Usuario
from app.routers.comum import templates
from app.security import verifica_senha

router = APIRouter(tags=["auth"])


@router.get("/login", response_class=HTMLResponse)
def tela_login(request: Request):
    if request.session.get("usuario_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"erro": None})


@router.post("/login")
def entrar(request: Request, email: str = Form(...), senha: str = Form(...),
           db: Session = Depends(get_db)):
    usuario = db.query(Usuario).filter_by(email=email.strip().lower(), ativo=True).first()
    if not usuario or not verifica_senha(senha, usuario.senha_hash):
        return templates.TemplateResponse(
            request, "login.html",
            {"erro": "E-mail ou senha incorretos. Confira os dados e tente de novo."},
            status_code=401)
    request.session["usuario_id"] = usuario.id
    request.session["empresa_id"] = usuario.empresa_id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def sair(request: Request, _: None = Depends(verifica_csrf)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
