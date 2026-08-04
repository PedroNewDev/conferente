"""Aplicação FastAPI: monta os routers, a sessão e o agendador."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import SessionLocal
from app.models import Empresa, ExecucaoJob
from app.routers import (
    auth, estoque, financeiro, fornecedores, jobs, notas, painel, pedidos,
    produtos, simples,
)
from app.services.pipeline import executar_ciclo, fonte_configurada

scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")


def _para_cada_empresa(nome_job: str, funcao) -> None:
    """Executa a função para cada empresa ativa, com sessão própria.
    Falha em uma empresa não impede as demais."""
    db = SessionLocal()
    try:
        empresas = db.query(Empresa).filter_by(ativa=True).all()
        for empresa in empresas:
            try:
                funcao(db, empresa)
            except Exception as exc:  # noqa: BLE001 — isola a falha por empresa
                db.rollback()
                db.add(ExecucaoJob(empresa_id=empresa.id, job=nome_job,
                                   iniciado_em=datetime.now(timezone.utc),
                                   terminado_em=datetime.now(timezone.utc),
                                   sucesso=False, erro=str(exc)))
                db.commit()
    finally:
        db.close()


def job_ciclo_recebimento() -> None:
    _para_cada_empresa("ciclo_recebimento",
                       lambda db, e: executar_ciclo(db, e.id, fonte_configurada()))


def job_alerta_vencimentos() -> None:
    """Registra diariamente as contas próximas do vencimento."""
    from app.services.financeiro import contas_a_vencer

    def roda(db, empresa):
        parametro = empresa.parametro
        contas = contas_a_vencer(db, empresa.id, parametro.dias_alerta_vencimento)
        db.add(ExecucaoJob(
            empresa_id=empresa.id, job="alerta_vencimentos",
            iniciado_em=datetime.now(timezone.utc),
            terminado_em=datetime.now(timezone.utc), sucesso=True,
            resumo={"contas_a_vencer": len(contas),
                    "valor": str(sum((c.valor for c in contas), start=0))}))
        db.commit()

    _para_cada_empresa("alerta_vencimentos", roda)


def job_cobranca_bloqueadas() -> None:
    """Registra diariamente as notas bloqueadas pendentes de decisão."""
    from app.enums import StatusNota
    from app.models import NotaFiscal

    def roda(db, empresa):
        pendentes = db.query(NotaFiscal).filter_by(
            empresa_id=empresa.id, status=StatusNota.BLOQUEADA.value).count()
        db.add(ExecucaoJob(
            empresa_id=empresa.id, job="cobranca_bloqueadas",
            iniciado_em=datetime.now(timezone.utc),
            terminado_em=datetime.now(timezone.utc), sucesso=True,
            resumo={"notas_bloqueadas": pendentes}))
        db.commit()

    _para_cada_empresa("cobranca_bloqueadas", roda)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.AGENDADOR_ATIVO:
        scheduler.add_job(job_ciclo_recebimento, "interval",
                          minutes=settings.INTERVALO_CICLO_MINUTOS,
                          id="ciclo", max_instances=1)
        scheduler.add_job(job_alerta_vencimentos, "cron", hour=8, minute=0,
                          id="vencimentos")
        scheduler.add_job(job_cobranca_bloqueadas, "cron", hour=8, minute=5,
                          id="bloqueadas")
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title=settings.APP_NOME, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.APP_SECRET,
                   session_cookie="conferente_sessao")
ESTATICOS = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(ESTATICOS)), name="static")

for router in (auth.router, simples.router, painel.router, produtos.router,
               fornecedores.router, pedidos.router, notas.router, estoque.router,
               financeiro.router, jobs.router):
    app.include_router(router)


@app.get("/saude")
def saude() -> dict:
    return {"status": "ok", "app": settings.APP_NOME}


@app.exception_handler(404)
async def nao_encontrado(request: Request, exc):
    if request.url.path.startswith("/api"):
        from fastapi.responses import JSONResponse
        return JSONResponse({"detalhe": "Recurso não encontrado."}, status_code=404)
    return RedirectResponse("/", status_code=303)
