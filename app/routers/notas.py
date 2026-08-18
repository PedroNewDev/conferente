"""Notas fiscais: lista, detalhe, liberação, cancelamento, vínculo manual,
upload de XML e fila de ocorrências."""
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.csrf import verifica_csrf
from app.database import get_db
from app.enums import Severidade, StatusNota
from app.fontes.base import Anexo, Documento
from app.models import (
    Fornecedor, NotaFiscal, Ocorrencia, Parametro, PedidoCompra, Usuario,
)
from app.routers.comum import templates
from app.scoping import obtem_ou_404
from app.security import exige_papel, usuario_atual
from app.services.pipeline import ResumoCiclo, _processar_xml, aplicar_efeitos
from app.services import conciliacao
from app.services.validacao import registrar_ocorrencia, tem_bloqueante
from app.utils.formularios import ErroFormulario, data_do_form

router = APIRouter(tags=["notas"])


@router.get("/notas", response_class=HTMLResponse)
def lista_notas(request: Request, status: str = "", fornecedor_id: int = 0,
                inicio: str = "", fim: str = "", busca: str = "",
                db: Session = Depends(get_db),
                usuario: Usuario = Depends(usuario_atual)):
    consulta = db.query(NotaFiscal).filter(NotaFiscal.empresa_id == usuario.empresa_id)
    if status:
        consulta = consulta.filter(NotaFiscal.status == status)
    if fornecedor_id:
        consulta = consulta.filter(NotaFiscal.fornecedor_id == fornecedor_id)
    erro = None
    try:
        if inicio:
            consulta = consulta.filter(NotaFiscal.data_emissao >= data_do_form(inicio, "início"))
        if fim:
            consulta = consulta.filter(NotaFiscal.data_emissao <= data_do_form(fim, "fim"))
    except ErroFormulario as exc:
        erro = str(exc)
    if busca:
        b = busca.strip()
        if b.isdigit() and len(b) == 44:
            consulta = consulta.filter(NotaFiscal.chave == b)
        elif b.isdigit():
            consulta = consulta.filter(NotaFiscal.numero == int(b))
        else:
            consulta = consulta.filter(NotaFiscal.nome_emitente.ilike(f"%{b}%"))
    notas = consulta.order_by(NotaFiscal.recebida_em.desc()).limit(200).all()
    fornecedores = (db.query(Fornecedor)
                    .filter_by(empresa_id=usuario.empresa_id)
                    .order_by(Fornecedor.razao_social).all())
    return templates.TemplateResponse(request, "notas/lista.html", {
        "usuario": usuario, "ativo": "notas", "notas": notas,
        "fornecedores": fornecedores, "erro": erro,
        "filtros": {"status": status, "fornecedor_id": fornecedor_id,
                    "inicio": inicio, "fim": fim, "busca": busca},
    })


@router.get("/notas/{nota_id}", response_class=HTMLResponse)
def detalhe_nota(nota_id: int, request: Request, db: Session = Depends(get_db),
                 usuario: Usuario = Depends(usuario_atual)):
    nota = obtem_ou_404(db, NotaFiscal, nota_id, usuario.empresa_id, "Nota não encontrada.")
    pedidos_abertos = (db.query(PedidoCompra)
                       .filter(PedidoCompra.empresa_id == usuario.empresa_id,
                               PedidoCompra.fornecedor_id == nota.fornecedor_id,
                               PedidoCompra.status.in_(["aberto", "parcial"]))
                       .all())
    return templates.TemplateResponse(request, "notas/detalhe.html", {
        "usuario": usuario, "ativo": "notas", "nota": nota,
        "pedidos_abertos": pedidos_abertos,
    })


@router.get("/notas/{nota_id}/xml")
def baixar_xml(nota_id: int, db: Session = Depends(get_db),
               usuario: Usuario = Depends(usuario_atual)):
    nota = obtem_ou_404(db, NotaFiscal, nota_id, usuario.empresa_id, "Nota não encontrada.")
    if not nota.xml_path or not Path(nota.xml_path).is_file():
        raise HTTPException(404, "XML não encontrado para esta nota.")
    return FileResponse(nota.xml_path, filename=f"{nota.chave}.xml",
                        media_type="application/xml")


@router.post("/notas/{nota_id}/liberar")
def liberar_nota(nota_id: int, request: Request, justificativa: str = Form(...),
                 db: Session = Depends(get_db),
                 usuario: Usuario = Depends(exige_papel("comprador")),
                 _: None = Depends(verifica_csrf)):
    """Libera nota bloqueada mediante justificativa; aplica os efeitos e
    registra quem liberou."""
    nota = obtem_ou_404(db, NotaFiscal, nota_id, usuario.empresa_id, "Nota não encontrada.")
    if nota.status != StatusNota.BLOQUEADA.value:
        raise HTTPException(400, "Só é possível liberar notas bloqueadas.")
    if not justificativa.strip():
        raise HTTPException(400, "Informe a justificativa da liberação.")

    agora = datetime.now(timezone.utc)
    for oc in nota.ocorrencias:
        if oc.severidade == Severidade.BLOQUEANTE.value and not oc.resolvida:
            oc.resolvida = True
            oc.resolvida_por = usuario.id
            oc.resolvida_em = agora
            oc.observacao_resolucao = f"Liberação manual: {justificativa.strip()}"

    nota.status = StatusNota.APROVADA.value
    nota.aprovada_por = usuario.id
    nota.justificativa_liberacao = justificativa.strip()
    if nota.tipo_operacao == "compra":
        aplicar_efeitos(db, nota)
    db.commit()
    return RedirectResponse(f"/notas/{nota_id}", status_code=303)


@router.post("/notas/{nota_id}/cancelar")
def cancelar_nota(nota_id: int, motivo: str = Form(...),
                  db: Session = Depends(get_db),
                  usuario: Usuario = Depends(exige_papel("comprador")),
                  _: None = Depends(verifica_csrf)):
    nota = obtem_ou_404(db, NotaFiscal, nota_id, usuario.empresa_id, "Nota não encontrada.")
    if nota.status == StatusNota.APROVADA.value:
        raise HTTPException(400, "Nota aprovada não pode ser cancelada — os efeitos "
                                 "já foram aplicados.")
    nota.status = StatusNota.CANCELADA.value
    registrar_ocorrencia(db, usuario.empresa_id, "CANCELAMENTO",
                         Severidade.INFORMATIVA,
                         f"Nota cancelada por {usuario.nome}: {motivo.strip()}",
                         nota=nota)
    db.commit()
    return RedirectResponse(f"/notas/{nota_id}", status_code=303)


@router.post("/notas/{nota_id}/vincular-pedido")
def vincular_pedido_manual(nota_id: int, pedido_id: int = Form(...),
                           db: Session = Depends(get_db),
                           usuario: Usuario = Depends(exige_papel("comprador")),
                           _: None = Depends(verifica_csrf)):
    """Vincula manualmente um pedido e reexecuta a conciliação."""
    nota = obtem_ou_404(db, NotaFiscal, nota_id, usuario.empresa_id, "Nota não encontrada.")
    pedido = obtem_ou_404(db, PedidoCompra, pedido_id, usuario.empresa_id, "Pedido não encontrado.")
    if nota.status not in (StatusNota.BLOQUEADA.value, StatusNota.VALIDADA.value):
        raise HTTPException(400, "Vínculo manual só para notas bloqueadas ou validadas.")

    # limpa as ocorrências de conciliação anteriores e reconcilia
    for oc in list(nota.ocorrencias):
        if oc.tipo.startswith("P") and not oc.resolvida:
            db.delete(oc)
    db.flush()

    parametro = db.query(Parametro).filter_by(empresa_id=usuario.empresa_id).one()
    itens = nota.itens
    nota.pedido_id = pedido.id
    ocs = conciliacao.conciliar(db, usuario.empresa_id, parametro, nota, itens, pedido)
    if tem_bloqueante(ocs):
        nota.status = StatusNota.BLOQUEADA.value
    else:
        nota.status = StatusNota.APROVADA.value
        if nota.tipo_operacao == "compra":
            aplicar_efeitos(db, nota)
    db.commit()
    return RedirectResponse(f"/notas/{nota_id}", status_code=303)


@router.post("/notas/upload")
async def upload_xml(request: Request, arquivo: UploadFile,
                     db: Session = Depends(get_db),
                     usuario: Usuario = Depends(exige_papel("comprador")),
                     _: None = Depends(verifica_csrf)):
    """Upload manual de XML — usa a mesma pipeline do ciclo."""
    from app.models import Empresa
    conteudo = await arquivo.read()
    empresa = db.get(Empresa, usuario.empresa_id)
    parametro = db.query(Parametro).filter_by(empresa_id=usuario.empresa_id).one()
    documento = Documento(
        identificador=f"upload:{usuario.id}:{arquivo.filename}:{len(conteudo)}",
        assunto=arquivo.filename, remetente=usuario.email,
        recebido_em=datetime.now(timezone.utc),
        anexos=[Anexo(nome=arquivo.filename or "nota.xml", conteudo=conteudo, tipo="xml")],
    )
    resumo = ResumoCiclo()
    from app.services.nfe_parser import NFeParseError
    try:
        _processar_xml(db, empresa, parametro, documento, conteudo, None,
                       "upload", resumo)
        db.commit()
    except NFeParseError as exc:
        db.rollback()
        return templates.TemplateResponse(request, "notas/upload_erro.html", {
            "usuario": usuario, "ativo": "notas",
            "erro": f"O arquivo enviado não é uma NF-e válida: {exc}",
        }, status_code=400)
    if resumo.notas_ids:
        return RedirectResponse(f"/notas/{resumo.notas_ids[0]}", status_code=303)
    return RedirectResponse("/notas", status_code=303)


@router.get("/ocorrencias", response_class=HTMLResponse)
def lista_ocorrencias(request: Request, db: Session = Depends(get_db),
                      usuario: Usuario = Depends(usuario_atual)):
    ocorrencias = (db.query(Ocorrencia)
                   .filter(Ocorrencia.empresa_id == usuario.empresa_id,
                           Ocorrencia.resolvida.is_(False))
                   .order_by(Ocorrencia.criado_em.desc())
                   .limit(300).all())
    return templates.TemplateResponse(request, "ocorrencias/lista.html", {
        "usuario": usuario, "ativo": "ocorrencias", "ocorrencias": ocorrencias,
    })


@router.post("/ocorrencias/{ocorrencia_id}/resolver")
def resolver_ocorrencia(ocorrencia_id: int, observacao: str = Form(""),
                        db: Session = Depends(get_db),
                        usuario: Usuario = Depends(exige_papel("comprador", "financeiro")),
                        _: None = Depends(verifica_csrf)):
    oc = obtem_ou_404(db, Ocorrencia, ocorrencia_id, usuario.empresa_id,
                       "Ocorrência não encontrada.")
    oc.resolvida = True
    oc.resolvida_por = usuario.id
    oc.resolvida_em = datetime.now(timezone.utc)
    oc.observacao_resolucao = observacao.strip() or "Resolvida pela fila de ocorrências."
    db.commit()
    return RedirectResponse("/ocorrencias", status_code=303)
