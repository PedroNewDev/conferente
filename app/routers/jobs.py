"""Histórico de execuções, disparo manual do ciclo e API JSON."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.models import ExecucaoJob, NotaFiscal, Ocorrencia, Produto, Usuario
from app.routers.comum import templates
from app.routers.painel import indicadores
from app.security import exige_papel, usuario_atual
from app.services.pipeline import executar_ciclo, fonte_configurada

router = APIRouter(tags=["jobs"])


@router.get("/jobs", response_class=HTMLResponse)
def historico(request: Request, db: Session = Depends(get_db),
              usuario: Usuario = Depends(usuario_atual)):
    execucoes = (db.query(ExecucaoJob)
                 .filter(ExecucaoJob.empresa_id == usuario.empresa_id)
                 .order_by(ExecucaoJob.iniciado_em.desc())
                 .limit(50).all())
    return templates.TemplateResponse(request, "jobs/lista.html", {
        "usuario": usuario, "ativo": "jobs", "execucoes": execucoes,
    })


@router.post("/jobs/executar-ciclo")
def executar_agora(db: Session = Depends(get_db),
                   usuario: Usuario = Depends(exige_papel("comprador")),
                   _: None = Depends(verifica_csrf)):
    """O botão da demonstração: dispara um ciclo imediatamente."""
    executar_ciclo(db, usuario.empresa_id, fonte_configurada())
    return RedirectResponse("/jobs", status_code=303)


# ------------------------------- API JSON ---------------------------------

@router.get("/api/notas")
def api_notas(db: Session = Depends(get_db),
              usuario: Usuario = Depends(usuario_atual)):
    notas = (db.query(NotaFiscal)
             .filter_by(empresa_id=usuario.empresa_id)
             .order_by(NotaFiscal.recebida_em.desc()).limit(100).all())
    return [{"id": n.id, "chave": n.chave, "numero": n.numero,
             "fornecedor": n.nome_emitente, "status": n.status,
             "valor_total": str(n.valor_total)} for n in notas]


@router.get("/api/notas/{nota_id}")
def api_nota(nota_id: int, db: Session = Depends(get_db),
             usuario: Usuario = Depends(usuario_atual)):
    n = (db.query(NotaFiscal)
         .filter_by(id=nota_id, empresa_id=usuario.empresa_id).first())
    if not n:
        raise HTTPException(404, "Nota não encontrada.")
    return {
        "id": n.id, "chave": n.chave, "numero": n.numero, "serie": n.serie,
        "status": n.status, "tipo_operacao": n.tipo_operacao,
        "fornecedor": n.nome_emitente, "valor_total": str(n.valor_total),
        "itens": [{"n_item": i.n_item, "descricao": i.descricao,
                   "quantidade": str(i.quantidade),
                   "valor_unitario": str(i.valor_unitario),
                   "valor_total": str(i.valor_total)} for i in n.itens],
        "ocorrencias": [{"tipo": o.tipo, "severidade": o.severidade,
                         "mensagem": o.mensagem,
                         "valor_impacto": str(o.valor_impacto) if o.valor_impacto else None,
                         "resolvida": o.resolvida} for o in n.ocorrencias],
    }


@router.get("/api/estoque")
def api_estoque(db: Session = Depends(get_db),
                usuario: Usuario = Depends(usuario_atual)):
    produtos = (db.query(Produto)
                .filter_by(empresa_id=usuario.empresa_id, ativo=True).all())
    return [{"codigo": p.codigo_interno, "descricao": p.descricao,
             "estoque_atual": str(p.estoque_atual),
             "estoque_minimo": str(p.estoque_minimo),
             "custo_medio": str(p.custo_medio)} for p in produtos]


@router.get("/api/ocorrencias")
def api_ocorrencias(db: Session = Depends(get_db),
                    usuario: Usuario = Depends(usuario_atual)):
    ocorrencias = (db.query(Ocorrencia)
                   .filter_by(empresa_id=usuario.empresa_id, resolvida=False)
                   .order_by(Ocorrencia.criado_em.desc()).limit(200).all())
    return [{"id": o.id, "tipo": o.tipo, "severidade": o.severidade,
             "mensagem": o.mensagem, "nota_id": o.nota_id,
             "valor_impacto": str(o.valor_impacto) if o.valor_impacto else None}
            for o in ocorrencias]


@router.get("/api/indicadores")
def api_indicadores(db: Session = Depends(get_db),
                    usuario: Usuario = Depends(usuario_atual)):
    dados = indicadores(db, usuario.empresa_id)
    return {
        "notas_hoje": len(dados["notas_hoje"]),
        "aprovadas_hoje": dados["aprovadas_hoje"],
        "notas_bloqueadas": dados["bloqueadas_total"],
        "impacto_em_aberto": str(dados["impacto_aberto"]),
        "contas_em_aberto": str(dados["contas_total_aberto"]),
    }


@router.post("/api/ciclo/executar")
def api_executar_ciclo(db: Session = Depends(get_db),
                       usuario: Usuario = Depends(exige_papel("comprador"))):
    resumo = executar_ciclo(db, usuario.empresa_id, fonte_configurada())
    return resumo.como_dict()
