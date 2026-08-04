"""Rotas de exportação para outro sistema: arquivo JSON e consulta pela API."""
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Empresa, NotaFiscal, Usuario
from app.security import usuario_atual
from app.services.exportacao import montar_pacote, nota_para_dict, notas_para_exportar

router = APIRouter(tags=["exportação"])


def _arquivo_json(dados: dict, nome: str) -> Response:
    """Devolve o JSON como download, formatado para ser legível por humanos."""
    corpo = json.dumps(dados, ensure_ascii=False, indent=2)
    return Response(
        content=corpo,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


@router.get("/exportar.json")
def exportar_lote(status: str = "aprovada", db: Session = Depends(get_db),
                  usuario: Usuario = Depends(usuario_atual)):
    """Baixa as notas conferidas para importar no ERP principal.

    Sem parâmetro, exporta apenas as aprovadas — as bloqueadas ainda dependem
    de decisão e não devem virar lançamento em outro sistema.
    """
    empresa = db.get(Empresa, usuario.empresa_id)
    notas = notas_para_exportar(db, usuario.empresa_id, status or None)
    nome = f"conferente_{status or 'todas'}_{len(notas)}notas.json"
    return _arquivo_json(montar_pacote(empresa, notas), nome)


@router.get("/notas/{nota_id}/exportar.json")
def exportar_nota(nota_id: int, db: Session = Depends(get_db),
                  usuario: Usuario = Depends(usuario_atual)):
    """Baixa uma nota específica."""
    nota = (db.query(NotaFiscal)
            .filter_by(id=nota_id, empresa_id=usuario.empresa_id).first())
    if not nota:
        raise HTTPException(404, "Nota não encontrada.")
    empresa = db.get(Empresa, usuario.empresa_id)
    return _arquivo_json(montar_pacote(empresa, [nota]),
                         f"nota_{nota.numero}_{nota.chave[:8]}.json")


@router.get("/api/exportacao")
def api_exportacao(status: str = "aprovada", db: Session = Depends(get_db),
                   usuario: Usuario = Depends(usuario_atual)):
    """Mesmo conteúdo do arquivo, para o ERP consumir direto por integração."""
    empresa = db.get(Empresa, usuario.empresa_id)
    return montar_pacote(empresa, notas_para_exportar(db, usuario.empresa_id,
                                                      status or None))


@router.get("/api/notas/{nota_id}/exportacao")
def api_exportacao_nota(nota_id: int, db: Session = Depends(get_db),
                        usuario: Usuario = Depends(usuario_atual)):
    nota = (db.query(NotaFiscal)
            .filter_by(id=nota_id, empresa_id=usuario.empresa_id).first())
    if not nota:
        raise HTTPException(404, "Nota não encontrada.")
    return nota_para_dict(nota)
