"""Autenticação: login, logout, cadastro de conta nova."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.models import Empresa, Parametro, Usuario
from app.rate_limit import limpa, registra_falha, segundos_bloqueado
from app.routers.comum import templates
from app.security import hash_senha, verifica_senha
from app.utils.documentos import cnpj_valido, so_digitos

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


@router.get("/cadastro", response_class=HTMLResponse)
def tela_cadastro(request: Request):
    if request.session.get("usuario_id"):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "cadastro.html", {"erro": None})


@router.post("/cadastro")
def cadastrar(request: Request, empresa_nome: str = Form(...), cnpj: str = Form(...),
             nome: str = Form(...), email: str = Form(...), senha: str = Form(...),
             confirma_senha: str = Form(...), db: Session = Depends(get_db),
             _: None = Depends(verifica_csrf)):
    def erro(msg: str, status_code: int = 400):
        return templates.TemplateResponse(
            request, "cadastro.html", {"erro": msg}, status_code=status_code)

    email = email.strip().lower()
    digitos_cnpj = so_digitos(cnpj)

    if not cnpj_valido(digitos_cnpj):
        return erro("CNPJ inválido — confira os dígitos.")
    if len(senha) < 8:
        return erro("A senha precisa ter pelo menos 8 caracteres.")
    if senha != confirma_senha:
        return erro("As senhas não coincidem.")
    if db.query(Usuario).filter_by(email=email).first():
        return erro("Já existe uma conta com este e-mail.")

    empresa = Empresa(razao_social=empresa_nome.strip(), cnpj=digitos_cnpj)
    db.add(empresa)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return erro("Já existe uma empresa cadastrada com este CNPJ.")

    db.add(Parametro(empresa_id=empresa.id))
    usuario = Usuario(empresa_id=empresa.id, nome=nome.strip(), email=email,
                      senha_hash=hash_senha(senha), papel="admin")
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return erro("Já existe uma conta com este e-mail.")

    request.session["usuario_id"] = usuario.id
    request.session["empresa_id"] = usuario.empresa_id
    return RedirectResponse("/", status_code=303)


@router.post("/logout")
def sair(request: Request, _: None = Depends(verifica_csrf)):
    request.session.clear()
    return RedirectResponse("/login", status_code=303)
