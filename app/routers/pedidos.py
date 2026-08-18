"""Pedidos de compra e seus itens."""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Fornecedor, PedidoCompra, PedidoItem, Produto, Usuario
from app.routers.comum import templates
from app.security import exige_papel, usuario_atual

router = APIRouter(tags=["pedidos"])


def _pedido(db: Session, empresa_id: int, pedido_id: int) -> PedidoCompra:
    pedido = db.query(PedidoCompra).filter_by(id=pedido_id, empresa_id=empresa_id).first()
    if not pedido:
        raise HTTPException(404, "Pedido não encontrado.")
    return pedido


@router.get("/pedidos", response_class=HTMLResponse)
def lista(request: Request, status: str = "", db: Session = Depends(get_db),
          usuario: Usuario = Depends(usuario_atual)):
    consulta = db.query(PedidoCompra).filter_by(empresa_id=usuario.empresa_id)
    if status:
        consulta = consulta.filter(PedidoCompra.status == status)
    pedidos = consulta.order_by(PedidoCompra.data_emissao.desc()).all()
    fornecedores = (db.query(Fornecedor)
                    .filter_by(empresa_id=usuario.empresa_id, ativo=True)
                    .order_by(Fornecedor.razao_social).all())
    return templates.TemplateResponse(request, "pedidos/lista.html", {
        "usuario": usuario, "ativo": "pedidos", "pedidos": pedidos,
        "fornecedores": fornecedores, "status_filtro": status,
        "hoje": date.today().isoformat(),
    })


@router.post("/pedidos")
def criar(numero: str = Form(...), fornecedor_id: int = Form(...),
          data_emissao: str = Form(...), frete_previsto: str = Form("0"),
          observacao: str = Form(""),
          db: Session = Depends(get_db),
          usuario: Usuario = Depends(exige_papel("comprador"))):
    fornecedor = db.query(Fornecedor).filter_by(id=fornecedor_id, empresa_id=usuario.empresa_id).first()
    if not fornecedor:
        raise HTTPException(404, "Fornecedor não encontrado.")
    pedido = PedidoCompra(
        empresa_id=usuario.empresa_id, numero=numero.strip(),
        fornecedor_id=fornecedor_id,
        data_emissao=date.fromisoformat(data_emissao),
        frete_previsto=Decimal(frete_previsto or "0"),
        observacao=observacao.strip() or None)
    db.add(pedido)
    db.commit()
    return RedirectResponse(f"/pedidos/{pedido.id}", status_code=303)


@router.get("/pedidos/{pedido_id}", response_class=HTMLResponse)
def detalhe(pedido_id: int, request: Request, db: Session = Depends(get_db),
            usuario: Usuario = Depends(usuario_atual)):
    pedido = _pedido(db, usuario.empresa_id, pedido_id)
    produtos = (db.query(Produto)
                .filter_by(empresa_id=usuario.empresa_id, ativo=True)
                .order_by(Produto.descricao).all())
    return templates.TemplateResponse(request, "pedidos/detalhe.html", {
        "usuario": usuario, "ativo": "pedidos", "pedido": pedido,
        "produtos": produtos,
    })


@router.post("/pedidos/{pedido_id}/itens")
def adicionar_item(pedido_id: int, produto_id: int = Form(...),
                   quantidade: str = Form(...), preco_unitario: str = Form(...),
                   db: Session = Depends(get_db),
                   usuario: Usuario = Depends(exige_papel("comprador"))):
    pedido = _pedido(db, usuario.empresa_id, pedido_id)
    if pedido.status not in ("aberto", "parcial"):
        raise HTTPException(400, "Só é possível incluir itens em pedido aberto.")
    produto = db.query(Produto).filter_by(id=produto_id, empresa_id=usuario.empresa_id).first()
    if not produto:
        raise HTTPException(404, "Produto não encontrado.")
    qtd = Decimal(quantidade)
    preco = Decimal(preco_unitario)
    db.add(PedidoItem(pedido_id=pedido.id, produto_id=produto_id,
                      quantidade=qtd, preco_unitario=preco,
                      valor_total=(qtd * preco).quantize(Decimal("0.01"))))
    pedido.valor_total = Decimal(pedido.valor_total) + (qtd * preco).quantize(Decimal("0.01"))
    db.commit()
    return RedirectResponse(f"/pedidos/{pedido_id}", status_code=303)


@router.post("/pedidos/{pedido_id}/cancelar")
def cancelar(pedido_id: int, db: Session = Depends(get_db),
             usuario: Usuario = Depends(exige_papel("comprador"))):
    pedido = _pedido(db, usuario.empresa_id, pedido_id)
    if pedido.status == "atendido":
        raise HTTPException(400, "Pedido já atendido não pode ser cancelado.")
    pedido.status = "cancelado"
    db.commit()
    return RedirectResponse("/pedidos", status_code=303)
