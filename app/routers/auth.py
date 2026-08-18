"""Autenticação: login, logout."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.models import Usuario
from app.rate_limit import limpa, registra_falha, segundos_bloqueado
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
    ip = request.client.host if request.client else "desconhecido"
    restante = segundos_bloqueado(email, ip)
    if restante:
        minutos = int(restante // 60) + 1
        return templates.TemplateResponse(
            request, "login.html",
            {"erro": f"Muitas tentativas. Tente novamente em {minutos} minuto(s)."},
            status_code=429)

    usuario = db.query(Usuario).filter_by(email=email.strip().lower(), ativo=True).first()
    if not usuario or not verifica_senha(senha, usuario.senha_hash):
        registra_falha(email, ip)
        return templates.TemplateResponse(
            request, "login.html",
            {"erro": "E-mail ou senha incorretos. Confira os dados e tente de novo."},
            status_code=401)
    limpa(email, ip)
    request.session["usuario_id"] = usuario.id
    request.session["empresa_id"] = usuario.empresa_id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def sair(request: Request, _: None = Depends(verifica_csrf)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
