"""Posição de estoque, extrato de movimentos e ajuste manual."""
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.models import MovimentoEstoque, Produto, Usuario
from app.routers.comum import templates
from app.scoping import obtem_ou_404
from app.security import exige_papel, usuario_atual
from app.services.estoque import registrar_ajuste

router = APIRouter(tags=["estoque"])


@router.get("/estoque", response_class=HTMLResponse)
def posicao(request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(usuario_atual)):
    produtos = (db.query(Produto)
                .filter_by(empresa_id=usuario.empresa_id, ativo=True)
                .order_by(Produto.descricao).all())
    return templates.TemplateResponse(request, "estoque/lista.html", {
        "usuario": usuario, "ativo": "estoque", "produtos": produtos,
    })


@router.get("/estoque/{produto_id}/movimentos", response_class=HTMLResponse)
def movimentos(produto_id: int, request: Request, db: Session = Depends(get_db),
               usuario: Usuario = Depends(usuario_atual)):
    produto = obtem_ou_404(db, Produto, produto_id, usuario.empresa_id, "Produto não encontrado.")
    extrato = (db.query(MovimentoEstoque)
               .filter_by(empresa_id=usuario.empresa_id, produto_id=produto_id)
               .order_by(MovimentoEstoque.criado_em.desc())
               .limit(200).all())
    return templates.TemplateResponse(request, "estoque/movimentos.html", {
        "usuario": usuario, "ativo": "estoque", "produto": produto,
        "movimentos": extrato,
    })


@router.post("/estoque/{produto_id}/ajuste")
def ajuste(produto_id: int, novo_saldo: str = Form(...),
           justificativa: str = Form(...),
           db: Session = Depends(get_db),
           usuario: Usuario = Depends(exige_papel("comprador")),
           _: None = Depends(verifica_csrf)):
    if not justificativa.strip():
        raise HTTPException(400, "Informe a justificativa do ajuste.")
    obtem_ou_404(db, Produto, produto_id, usuario.empresa_id, "Produto não encontrado.")
    registrar_ajuste(db, usuario.empresa_id, produto_id,
                     Decimal(novo_saldo), usuario.id, justificativa.strip())
    db.commit()
    return RedirectResponse(f"/estoque/{produto_id}/movimentos", status_code=303)
