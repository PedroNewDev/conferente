"""Painel: indicadores do dia, divergências, estoque mínimo, vencimentos."""
from datetime import date, datetime, time, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import StatusConta, StatusNota
from app.models import ContaPagar, Empresa, ExecucaoJob, NotaFiscal, Ocorrencia, Usuario
from app.routers.comum import templates
from app.security import usuario_atual
from app.services.estoque import produtos_abaixo_do_minimo
from app.services.financeiro import contas_a_vencer

router = APIRouter(tags=["painel"])


def indicadores(db: Session, empresa_id: int) -> dict:
    hoje_inicio = datetime.combine(date.today(), time.min).astimezone(timezone.utc)
    notas_hoje = (db.query(NotaFiscal)
                  .filter(NotaFiscal.empresa_id == empresa_id,
                          NotaFiscal.recebida_em >= hoje_inicio)
                  .order_by(NotaFiscal.recebida_em.desc())
                  .all())
    divergencias = (db.query(Ocorrencia)
                    .filter(Ocorrencia.empresa_id == empresa_id,
                            Ocorrencia.resolvida.is_(False),
                            Ocorrencia.severidade.in_(["bloqueante", "alerta"]))
                    .order_by(Ocorrencia.criado_em.desc())
                    .limit(8).all())
    impacto_aberto = (db.query(func.coalesce(func.sum(Ocorrencia.valor_impacto), 0))
                      .filter(Ocorrencia.empresa_id == empresa_id,
                              Ocorrencia.resolvida.is_(False))
                      .scalar())
    bloqueadas = (db.query(NotaFiscal)
                  .filter_by(empresa_id=empresa_id, status=StatusNota.BLOQUEADA.value)
                  .count())
    total_aberto = (db.query(func.coalesce(func.sum(ContaPagar.valor), 0))
                    .filter(ContaPagar.empresa_id == empresa_id,
                            ContaPagar.status == StatusConta.ABERTA.value)
                    .scalar())
    return {
        "notas_hoje": notas_hoje,
        "aprovadas_hoje": sum(1 for n in notas_hoje if n.status == "aprovada"),
        "bloqueadas_total": bloqueadas,
        "divergencias": divergencias,
        "impacto_aberto": Decimal(impacto_aberto or 0),
        "contas_total_aberto": Decimal(total_aberto or 0),
    }


@router.get("/", response_class=HTMLResponse)
def painel(request: Request, db: Session = Depends(get_db),
           usuario: Usuario = Depends(usuario_atual)):
    empresa = db.get(Empresa, usuario.empresa_id)
    dados = indicadores(db, usuario.empresa_id)
    abaixo_minimo = produtos_abaixo_do_minimo(db, usuario.empresa_id)
    a_vencer = contas_a_vencer(db, usuario.empresa_id,
                               empresa.parametro.dias_alerta_vencimento)
    execucoes = (db.query(ExecucaoJob)
                 .filter(ExecucaoJob.empresa_id == usuario.empresa_id)
                 .order_by(ExecucaoJob.iniciado_em.desc())
                 .limit(5).all())
    return templates.TemplateResponse(request, "painel.html", {
        "usuario": usuario, "empresa": empresa, "ativo": "painel",
        **dados,
        "abaixo_minimo": abaixo_minimo,
        "a_vencer": a_vencer,
        "execucoes": execucoes,
    })
