"""Contas a pagar: lista com filtros e baixa."""
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ContaPagar, Usuario
from app.routers.comum import templates
from app.security import exige_papel, usuario_atual
from app.services.financeiro import marcar_paga

router = APIRouter(tags=["financeiro"])


@router.get("/financeiro/contas", response_class=HTMLResponse)
def contas(request: Request, status: str = "aberta", db: Session = Depends(get_db),
           usuario: Usuario = Depends(usuario_atual)):
    consulta = db.query(ContaPagar).filter_by(empresa_id=usuario.empresa_id)
    if status:
        consulta = consulta.filter(ContaPagar.status == status)
    lista = consulta.order_by(ContaPagar.vencimento).limit(300).all()
    return templates.TemplateResponse(request, "financeiro/contas.html", {
        "usuario": usuario, "ativo": "financeiro", "contas": lista,
        "status_filtro": status, "hoje": date.today(),
    })


@router.post("/financeiro/contas/{conta_id}/pagar")
def pagar(conta_id: int, data_pagamento: str = Form(""),
          db: Session = Depends(get_db),
          usuario: Usuario = Depends(exige_papel("financeiro"))):
    quando = date.fromisoformat(data_pagamento) if data_pagamento else date.today()
    try:
        marcar_paga(db, usuario.empresa_id, conta_id, quando)
    except Exception:
        raise HTTPException(404, "Conta não encontrada.")
    db.commit()
    return RedirectResponse("/financeiro/contas", status_code=303)
