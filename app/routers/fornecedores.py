"""Cadastro de fornecedores."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.models import Fornecedor, Usuario
from app.routers.comum import templates
from app.scoping import obtem_ou_404
from app.security import exige_papel, usuario_atual
from app.utils.documentos import cnpj_valido, so_digitos

router = APIRouter(tags=["fornecedores"])


@router.get("/fornecedores", response_class=HTMLResponse)
def lista(request: Request, db: Session = Depends(get_db),
          usuario: Usuario = Depends(usuario_atual)):
    fornecedores = (db.query(Fornecedor)
                    .filter_by(empresa_id=usuario.empresa_id)
                    .order_by(Fornecedor.razao_social).all())
    return templates.TemplateResponse(request, "fornecedores/lista.html", {
        "usuario": usuario, "ativo": "fornecedores", "fornecedores": fornecedores,
        "erro": request.query_params.get("erro"),
    })


@router.post("/fornecedores")
def criar(cnpj: str = Form(...), razao_social: str = Form(...),
          nome_fantasia: str = Form(""), uf: str = Form(""),
          municipio: str = Form(""), email: str = Form(""),
          db: Session = Depends(get_db),
          usuario: Usuario = Depends(exige_papel("comprador")),
          _: None = Depends(verifica_csrf)):
    digitos = so_digitos(cnpj)
    if not cnpj_valido(digitos):
        return RedirectResponse(
            "/fornecedores?erro=CNPJ inválido — confira os dígitos.",
            status_code=303)
    db.add(Fornecedor(empresa_id=usuario.empresa_id, cnpj=digitos,
                      razao_social=razao_social.strip(),
                      nome_fantasia=nome_fantasia.strip() or None,
                      uf=uf.strip().upper() or None,
                      municipio=municipio.strip() or None,
                      email=email.strip() or None))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            "/fornecedores?erro=Já existe fornecedor cadastrado com este CNPJ.",
            status_code=303)
    return RedirectResponse("/fornecedores", status_code=303)


@router.post("/fornecedores/{fornecedor_id}")
def editar(fornecedor_id: int, razao_social: str = Form(...),
           nome_fantasia: str = Form(""), uf: str = Form(""),
           municipio: str = Form(""), email: str = Form(""),
           ativo: str = Form("sim"),
           db: Session = Depends(get_db),
           usuario: Usuario = Depends(exige_papel("comprador")),
           _: None = Depends(verifica_csrf)):
    fornecedor = obtem_ou_404(db, Fornecedor, fornecedor_id, usuario.empresa_id,
                               "Fornecedor não encontrado.")
    fornecedor.razao_social = razao_social.strip()
    fornecedor.nome_fantasia = nome_fantasia.strip() or None
    fornecedor.uf = uf.strip().upper() or None
    fornecedor.municipio = municipio.strip() or None
    fornecedor.email = email.strip() or None
    fornecedor.ativo = ativo == "sim"
    db.commit()
    return RedirectResponse("/fornecedores", status_code=303)
