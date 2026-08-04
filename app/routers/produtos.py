"""Cadastro de produtos e de-para de códigos por fornecedor."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Fornecedor, Produto, ProdutoFornecedor, Usuario
from app.routers.comum import templates
from app.security import exige_papel, usuario_atual

router = APIRouter(tags=["produtos"])


def _produto(db: Session, empresa_id: int, produto_id: int) -> Produto:
    produto = db.query(Produto).filter_by(id=produto_id, empresa_id=empresa_id).first()
    if not produto:
        raise HTTPException(404, "Produto não encontrado.")
    return produto


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
    })


@router.post("/produtos")
def criar(codigo_interno: str = Form(...), descricao: str = Form(...),
          unidade: str = Form(...), ncm: str = Form(""),
          estoque_minimo: str = Form("0"),
          db: Session = Depends(get_db),
          usuario: Usuario = Depends(exige_papel("comprador"))):
    db.add(Produto(empresa_id=usuario.empresa_id,
                   codigo_interno=codigo_interno.strip(),
                   descricao=descricao.strip(), unidade=unidade.strip(),
                   ncm=ncm.strip() or None,
                   estoque_minimo=Decimal(estoque_minimo or "0")))
    db.commit()
    return RedirectResponse("/produtos", status_code=303)


@router.get("/produtos/{produto_id}", response_class=HTMLResponse)
def detalhe(produto_id: int, request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(usuario_atual)):
    produto = _produto(db, usuario.empresa_id, produto_id)
    vinculos = (db.query(ProdutoFornecedor)
                .filter_by(empresa_id=usuario.empresa_id, produto_id=produto_id)
                .all())
    fornecedores = (db.query(Fornecedor)
                    .filter_by(empresa_id=usuario.empresa_id, ativo=True)
                    .order_by(Fornecedor.razao_social).all())
    return templates.TemplateResponse(request, "produtos/detalhe.html", {
        "usuario": usuario, "ativo": "produtos", "produto": produto,
        "vinculos": vinculos, "fornecedores": fornecedores,
    })


@router.post("/produtos/{produto_id}")
def editar(produto_id: int, descricao: str = Form(...), unidade: str = Form(...),
           ncm: str = Form(""), estoque_minimo: str = Form("0"),
           ativo: str = Form("sim"),
           db: Session = Depends(get_db),
           usuario: Usuario = Depends(exige_papel("comprador"))):
    produto = _produto(db, usuario.empresa_id, produto_id)
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
                  usuario: Usuario = Depends(exige_papel("comprador"))):
    _produto(db, usuario.empresa_id, produto_id)
    db.add(ProdutoFornecedor(
        empresa_id=usuario.empresa_id, produto_id=produto_id,
        fornecedor_id=fornecedor_id,
        codigo_no_fornecedor=codigo_no_fornecedor.strip(),
        ean=ean.strip() or None))
    db.commit()
    return RedirectResponse(f"/produtos/{produto_id}", status_code=303)
