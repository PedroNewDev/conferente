"""Modo automatizador: uma tela, um botão, resultado em linguagem comum.

É a porta de entrada do sistema. As telas completas de cadastro e gestão
continuam disponíveis a partir do painel, em /painel.
"""
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.enums import Severidade, StatusNota
from app.fontes.base import Anexo, Documento
from app.models import Empresa, ExecucaoJob, NotaFiscal, Ocorrencia, Parametro, Usuario
from app.routers.comum import templates
from app.security import exige_papel, usuario_atual
from app.services.explicacoes import explicar
from app.services.nfe_parser import NFeParseError
from app.services.pipeline import (
    ResumoCiclo, _processar_xml, executar_ciclo, fonte_configurada,
)

router = APIRouter(tags=["automatizador"])

# Quantas notas a tela mostra por vez
LIMITE_NOTAS = 12


def _resumo_do_dinheiro(db: Session, empresa_id: int) -> dict:
    """Os dois números que interessam: o que foi barrado e o que isso vale."""
    impacto = (db.query(func.coalesce(func.sum(Ocorrencia.valor_impacto), 0))
               .filter(Ocorrencia.empresa_id == empresa_id,
                       Ocorrencia.resolvida.is_(False))
               .scalar())
    barradas = (db.query(NotaFiscal)
                .filter(NotaFiscal.empresa_id == empresa_id,
                        NotaFiscal.status.in_([StatusNota.BLOQUEADA.value,
                                               StatusNota.REJEITADA.value]))
                .count())
    return {"impacto": Decimal(impacto or 0), "barradas": barradas}


def _motivos(nota: NotaFiscal) -> list[dict]:
    """Ocorrências da nota em linguagem comum, sem os códigos técnicos."""
    vistos: set[str] = set()
    motivos: list[dict] = []
    for oc in nota.ocorrencias:
        if oc.tipo in vistos or oc.severidade == Severidade.INFORMATIVA.value:
            continue
        vistos.add(oc.tipo)
        motivos.append({
            "texto": explicar(oc.tipo),
            "grave": oc.severidade == Severidade.BLOQUEANTE.value,
            "valor": Decimal(oc.valor_impacto) if oc.valor_impacto else None,
        })
    return motivos


@router.get("/", response_class=HTMLResponse)
def automatizador(request: Request, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(usuario_atual)):
    empresa = db.get(Empresa, usuario.empresa_id)
    notas = (db.query(NotaFiscal)
             .filter(NotaFiscal.empresa_id == usuario.empresa_id)
             .order_by(NotaFiscal.recebida_em.desc())
             .limit(LIMITE_NOTAS).all())
    total = (db.query(NotaFiscal)
             .filter(NotaFiscal.empresa_id == usuario.empresa_id).count())
    ultima = (db.query(ExecucaoJob)
              .filter(ExecucaoJob.empresa_id == usuario.empresa_id,
                      ExecucaoJob.job == "ciclo_recebimento")
              .order_by(ExecucaoJob.iniciado_em.desc())
              .first())

    return templates.TemplateResponse(request, "simples.html", {
        "usuario": usuario, "empresa": empresa,
        "notas": [{"nota": n, "motivos": _motivos(n)} for n in notas],
        "total_notas": total,
        "ultima_execucao": ultima,
        "erro": request.query_params.get("erro"),
        **_resumo_do_dinheiro(db, usuario.empresa_id),
    })


@router.post("/processar")
def processar(db: Session = Depends(get_db),
              usuario: Usuario = Depends(exige_papel("comprador"))):
    """O botão: lê a pasta de entrada e processa tudo que estiver lá."""
    executar_ciclo(db, usuario.empresa_id, fonte_configurada())
    return RedirectResponse("/", status_code=303)


@router.post("/enviar")
async def enviar(arquivo: UploadFile, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(exige_papel("comprador"))):
    """Envio manual de um XML pela mesma esteira do ciclo automático."""
    conteudo = await arquivo.read()
    empresa = db.get(Empresa, usuario.empresa_id)
    parametro = db.query(Parametro).filter_by(empresa_id=usuario.empresa_id).one()
    documento = Documento(
        identificador=f"upload:{usuario.id}:{arquivo.filename}:{len(conteudo)}",
        assunto=arquivo.filename, remetente=usuario.email,
        recebido_em=datetime.now(timezone.utc),
        anexos=[Anexo(nome=arquivo.filename or "nota.xml",
                      conteudo=conteudo, tipo="xml")],
    )
    try:
        _processar_xml(db, empresa, parametro, documento, conteudo, None,
                       "upload", ResumoCiclo())
        db.commit()
    except NFeParseError:
        db.rollback()
        return RedirectResponse(
            "/?erro=O arquivo enviado não é uma nota fiscal válida.",
            status_code=303)
    return RedirectResponse("/", status_code=303)
