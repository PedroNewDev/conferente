"""Cadastro de produtos e de-para de códigos por fornecedor."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.models import Fornecedor, Produto, ProdutoFornecedor, Usuario
from app.routers.comum import templates
from app.scoping import obtem_ou_404
from app.security import exige_papel, usuario_atual

router = APIRouter(tags=["produtos"])


@router.get("/produtos", response_class=HTMLResponse)
def lista(request: Request, busca: str = "", db: Session = Depends(get_db),
          usuario: Usuario = Depends(usuario_atual)):
    consulta = db.query(Produto).filter_by(empresa_id=usuario.empresa_id)
    if busca:
        consulta = consulta.filter(Produto.descricao.ilike(f"%{busca}%")
                                   | Produto.codigo_interno.ilike(f"%{busca}%"))
    produtos = consulta.order_by(Produto.descricao).all()
    return templates.TemplateResponse(request, "produtos/lista.html", {
        "usuario": usuario, "ativo": "produtos", "produtos": produtos, "busca": busca,
        "erro": request.query_params.get("erro"),
    })


@router.post("/produtos")
def criar(codigo_interno: str = Form(...), descricao: str = Form(...),
          unidade: str = Form(...), ncm: str = Form(""),
          estoque_minimo: str = Form("0"),
          db: Session = Depends(get_db),
          usuario: Usuario = Depends(exige_papel("comprador")),
          _: None = Depends(verifica_csrf)):
    db.add(Produto(empresa_id=usuario.empresa_id,
                   codigo_interno=codigo_interno.strip(),
                   descricao=descricao.strip(), unidade=unidade.strip(),
                   ncm=ncm.strip() or None,
                   estoque_minimo=Decimal(estoque_minimo or "0")))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            "/produtos?erro=Já existe produto com este código interno.",
            status_code=303)
    return RedirectResponse("/produtos", status_code=303)


@router.get("/produtos/{produto_id}", response_class=HTMLResponse)
def detalhe(produto_id: int, request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(usuario_atual)):
    produto = obtem_ou_404(db, Produto, produto_id, usuario.empresa_id, "Produto não encontrado.")
    vinculos = (db.query(ProdutoFornecedor)
                .filter_by(empresa_id=usuario.empresa_id, produto_id=produto_id)
                .all())
    fornecedores = (db.query(Fornecedor)
                    .filter_by(empresa_id=usuario.empresa_id, ativo=True)
                    .order_by(Fornecedor.razao_social).all())
    return templates.TemplateResponse(request, "produtos/detalhe.html", {
        "usuario": usuario, "ativo": "produtos", "produto": produto,
        "vinculos": vinculos, "fornecedores": fornecedores,
        "erro": request.query_params.get("erro"),
    })


@router.post("/produtos/{produto_id}")
def editar(produto_id: int, descricao: str = Form(...), unidade: str = Form(...),
           ncm: str = Form(""), estoque_minimo: str = Form("0"),
           ativo: str = Form("sim"),
           db: Session = Depends(get_db),
           usuario: Usuario = Depends(exige_papel("comprador")),
           _: None = Depends(verifica_csrf)):
    produto = obtem_ou_404(db, Produto, produto_id, usuario.empresa_id, "Produto não encontrado.")
    produto.descricao = descricao.strip()
    produto.unidade = unidade.strip()
    produto.ncm = ncm.strip() or None
    produto.estoque_minimo = Decimal(estoque_minimo or "0")
    produto.ativo = ativo == "sim"
    db.commit()
    return RedirectResponse(f"/produtos/{produto_id}", status_code=303)


@router.post("/produtos/{produto_id}/vinculos")
def criar_vinculo(produto_id: int, fornecedor_id: int = Form(...),
                  codigo_no_fornecedor: str = Form(...), ean: str = Form(""),
                  db: Session = Depends(get_db),
                  usuario: Usuario = Depends(exige_papel("comprador")),
                  _: None = Depends(verifica_csrf)):
    obtem_ou_404(db, Produto, produto_id, usuario.empresa_id, "Produto não encontrado.")
    obtem_ou_404(db, Fornecedor, fornecedor_id, usuario.empresa_id, "Fornecedor não encontrado.")
    db.add(ProdutoFornecedor(
        empresa_id=usuario.empresa_id, produto_id=produto_id,
        fornecedor_id=fornecedor_id,
        codigo_no_fornecedor=codigo_no_fornecedor.strip(),
        ean=ean.strip() or None))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(
            f"/produtos/{produto_id}?erro=Já existe vínculo com este fornecedor e código.",
            status_code=303)
    return RedirectResponse(f"/produtos/{produto_id}", status_code=303)
