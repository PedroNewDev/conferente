"""Pipeline do ciclo de recebimento — orquestra fonte, parser, validação,
conciliação, efeitos, relatório e e-mail.

Tolerância a falha: cada documento e cada nota são processados em bloco
próprio; erro em um não interrompe o lote. Idempotência: documento já visto
(email_processado) e chave já lançada (V12) são pulados sem efeito.
"""
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.enums import Severidade, StatusEmail, StatusNota, StatusPedido, TipoOperacao
from app.fontes.base import Documento, FonteDeDocumentos
from app.models import (
    Duplicata, EmailProcessado, Empresa, ExecucaoJob, NotaFiscal, NotaItem, Parametro,
)
from app.services import conciliacao, estoque, financeiro
from app.services.nfe_parser import NFeParseError, NotaFiscalNFe, parse_nfe
from app.services.validacao import (
    registrar_ocorrencia, resolver_fornecedor, resolver_produtos, tem_bloqueante, validar_nota,
)


@dataclass
class ResumoCiclo:
    documentos_lidos: int = 0
    notas_novas: int = 0
    aprovadas: int = 0
    bloqueadas: int = 0
    rejeitadas: int = 0
    duplicatas_descartadas: int = 0
    quarentena: int = 0
    valor_aprovado: Decimal = Decimal("0")
    valor_bloqueado: Decimal = Decimal("0")
    impacto_divergencias: Decimal = Decimal("0")
    ocorrencias_por_tipo: dict = field(default_factory=dict)
    notas_ids: list = field(default_factory=list)
    erros: list = field(default_factory=list)

    def como_dict(self) -> dict:
        return {
            "documentos_lidos": self.documentos_lidos,
            "notas_novas": self.notas_novas,
            "aprovadas": self.aprovadas,
            "bloqueadas": self.bloqueadas,
            "rejeitadas": self.rejeitadas,
            "duplicatas_descartadas": self.duplicatas_descartadas,
            "quarentena": self.quarentena,
            "valor_aprovado": str(self.valor_aprovado),
            "valor_bloqueado": str(self.valor_bloqueado),
            "impacto_divergencias": str(self.impacto_divergencias),
            "ocorrencias_por_tipo": self.ocorrencias_por_tipo,
            "erros": self.erros,
        }


def _conta_ocorrencias(resumo: ResumoCiclo, ocorrencias) -> None:
    for oc in ocorrencias:
        resumo.ocorrencias_por_tipo[oc.tipo] = resumo.ocorrencias_por_tipo.get(oc.tipo, 0) + 1
        if oc.valor_impacto:
            resumo.impacto_divergencias += Decimal(oc.valor_impacto)


def aplicar_efeitos(db: Session, nota: NotaFiscal) -> None:
    """Efeitos de uma nota de compra aprovada: entrada de estoque, custo médio,
    baixa no pedido e contas a pagar. Chamado pelo pipeline e pela liberação manual."""
    itens = db.query(NotaItem).filter_by(nota_id=nota.id).all()

    for item in itens:
        if not item.produto_id:
            continue  # sem de-para (C02): não movimenta estoque
        estoque.registrar_entrada(
            db, nota.empresa_id, item.produto_id,
            Decimal(item.quantidade), Decimal(item.valor_unitario), nota.id)
        if item.pedido_item_id and item.pedido_item:
            item.pedido_item.quantidade_atendida = (
                Decimal(item.pedido_item.quantidade_atendida) + Decimal(item.quantidade))

    # status do pedido: atendido quando nada mais pende; parcial se algo entrou
    if nota.pedido_id and nota.pedido:
        pendentes = [pi for pi in nota.pedido.itens
                     if Decimal(pi.quantidade_atendida) < Decimal(pi.quantidade)]
        atendidos = [pi for pi in nota.pedido.itens
                     if Decimal(pi.quantidade_atendida) > 0]
        if not pendentes:
            nota.pedido.status = StatusPedido.ATENDIDO.value
        elif atendidos:
            nota.pedido.status = StatusPedido.PARCIAL.value

    financeiro.gerar_contas_a_pagar(db, nota)


def _arquivar(nota: NotaFiscal, xml: bytes, pdf: bytes | None) -> None:
    """Guarda legal: arquivo/{cnpj_emitente}/{ano}/{mes}/{chave}.xml"""
    emissao = nota.data_emissao
    pasta = Path(settings.PASTA_ARQUIVO) / nota.cnpj_emitente / f"{emissao.year}" / f"{emissao.month:02d}"
    pasta.mkdir(parents=True, exist_ok=True)
    caminho_xml = pasta / f"{nota.chave}.xml"
    caminho_xml.write_bytes(xml)
    nota.xml_path = str(caminho_xml)
    if pdf:
        caminho_pdf = pasta / f"{nota.chave}.pdf"
        caminho_pdf.write_bytes(pdf)
        nota.pdf_path = str(caminho_pdf)


def _processar_xml(db: Session, empresa: Empresa, parametro: Parametro,
                   documento: Documento, xml: bytes, pdf: bytes | None,
                   origem: str, resumo: ResumoCiclo) -> None:
    """Processa um anexo XML dentro do documento. Levanta NFeParseError para
    que o chamador trate a quarentena (V01)."""
    nfe: NotaFiscalNFe = parse_nfe(xml)

    # V12 — chave já lançada nesta empresa: descarta e registra a duplicidade
    existente = db.query(NotaFiscal).filter_by(
        empresa_id=empresa.id, chave=nfe.chave).first()
    if existente:
        oc = registrar_ocorrencia(
            db, empresa.id, "V12", Severidade.INFORMATIVA,
            f"Nota {nfe.numero} recebida novamente (chave já lançada). "
            "Documento descartado sem novo lançamento.",
            nota=existente, detalhe={"identificador": documento.identificador})
        _conta_ocorrencias(resumo, [oc])
        resumo.duplicatas_descartadas += 1
        return

    # Persiste a nota como recebida antes das validações, para que as
    # ocorrências possam referenciá-la.
    nota = NotaFiscal(
        empresa_id=empresa.id, chave=nfe.chave, numero=nfe.numero, serie=nfe.serie,
        modelo=nfe.modelo, data_emissao=nfe.data_emissao,
        cnpj_emitente=nfe.cnpj_emitente, nome_emitente=nfe.nome_emitente,
        cnpj_destinatario=nfe.cnpj_destinatario,
        natureza_operacao=nfe.natureza_operacao,
        valor_produtos=nfe.valor_produtos, valor_desconto=nfe.valor_desconto,
        valor_frete=nfe.valor_frete, valor_seguro=nfe.valor_seguro,
        valor_outros=nfe.valor_outros, valor_ipi=nfe.valor_ipi,
        valor_st=nfe.valor_st, valor_total=nfe.valor_total,
        status=StatusNota.RECEBIDA.value, origem=origem,
        email_message_id=documento.identificador,
    )
    db.add(nota)
    db.flush()
    resumo.notas_novas += 1
    resumo.notas_ids.append(nota.id)

    itens: list[NotaItem] = []
    for i in nfe.itens:
        item = NotaItem(
            nota_id=nota.id, n_item=i.n_item, codigo_fornecedor=i.codigo,
            ean=i.ean, descricao=i.descricao, ncm=i.ncm, cfop=i.cfop,
            unidade=i.unidade, quantidade=i.quantidade,
            valor_unitario=i.valor_unitario, valor_total=i.valor_total,
            numero_pedido_xml=i.numero_pedido, item_pedido_xml=i.item_pedido,
        )
        db.add(item)
        itens.append(item)
    for d in nfe.duplicatas:
        db.add(Duplicata(nota_id=nota.id, numero=d.numero,
                         vencimento=d.vencimento, valor=d.valor))
    db.flush()

    # Validações V02 a V11
    ocorrencias = validar_nota(db, empresa.cnpj, parametro, nfe, nota)
    _conta_ocorrencias(resumo, ocorrencias)
    if tem_bloqueante(ocorrencias):
        nota.status = StatusNota.REJEITADA.value
        nota.processada_em = datetime.now(timezone.utc)
        resumo.rejeitadas += 1
        _arquivar(nota, xml, pdf)
        return

    # Cadastro: fornecedor (C01) e produtos por de-para (C02/C03)
    fornecedor, ocs_c01 = resolver_fornecedor(db, empresa.id, nfe, nota)
    ocs_prod = resolver_produtos(db, empresa.id, fornecedor, nota, itens)
    _conta_ocorrencias(resumo, ocs_c01 + ocs_prod)

    nota.status = StatusNota.VALIDADA.value

    # Classificação por CFOP
    nota.cfop_predominante, nota.tipo_operacao = conciliacao.classificar_cfop(itens)
    oc_p09 = conciliacao.sinalizar_cfop_nao_venda(db, empresa.id, nota)
    if oc_p09:
        _conta_ocorrencias(resumo, [oc_p09])

    ocs_p: list = []
    if nota.tipo_operacao == TipoOperacao.COMPRA.value:
        # Vínculo com pedido e conciliação item a item
        pedido = conciliacao.vincular_pedido(db, empresa.id, nota, itens,
                                             nfe.numero_pedido_infcpl())
        ocs_p = conciliacao.conciliar(db, empresa.id, parametro, nota, itens, pedido)
        _conta_ocorrencias(resumo, ocs_p)
    else:
        oc = registrar_ocorrencia(
            db, empresa.id, "P09-INFO", Severidade.INFORMATIVA,
            f"Operação classificada como '{nota.tipo_operacao}': registrada "
            "sem efeito no estoque ou no financeiro.",
            nota=nota)
        _conta_ocorrencias(resumo, [oc])

    if tem_bloqueante(ocs_p):
        nota.status = StatusNota.BLOQUEADA.value
        resumo.bloqueadas += 1
        resumo.valor_bloqueado += Decimal(nota.valor_total or 0)
    else:
        nota.status = StatusNota.APROVADA.value
        resumo.aprovadas += 1
        resumo.valor_aprovado += Decimal(nota.valor_total or 0)
        if nota.tipo_operacao == TipoOperacao.COMPRA.value:
            aplicar_efeitos(db, nota)

    nota.processada_em = datetime.now(timezone.utc)
    _arquivar(nota, xml, pdf)


def executar_ciclo(db: Session, empresa_id: int, fonte: FonteDeDocumentos) -> ResumoCiclo:
    """Executa um ciclo completo de recebimento para uma empresa."""
    resumo = ResumoCiclo()
    inicio = datetime.now(timezone.utc)
    execucao = ExecucaoJob(empresa_id=empresa_id, job="ciclo_recebimento",
                           iniciado_em=inicio)
    db.add(execucao)
    db.commit()

    empresa = db.get(Empresa, empresa_id)
    parametro = db.query(Parametro).filter_by(empresa_id=empresa_id).one()

    # Falha de conexão com a fonte encerra o ciclo com erro registrado
    try:
        documentos = list(fonte.listar_novos())
    except Exception as exc:  # noqa: BLE001 — a fonte é externa (rede, disco)
        execucao.terminado_em = datetime.now(timezone.utc)
        execucao.sucesso = False
        execucao.erro = f"Falha ao listar documentos da fonte: {exc}"
        db.commit()
        resumo.erros.append(str(exc))
        return resumo

    for documento in documentos:
        resumo.documentos_lidos += 1
        savepoint = db.begin_nested()
        try:
            # Idempotência no nível do documento
            ja_visto = db.query(EmailProcessado).filter_by(
                empresa_id=empresa_id, message_id=documento.identificador).first()
            if ja_visto:
                savepoint.commit()
                continue

            xmls = [a for a in documento.anexos if a.tipo == "xml"]
            pdfs = [a for a in documento.anexos if a.tipo == "pdf"]
            if not xmls:
                motivo = "Nenhum anexo XML de NF-e encontrado no documento."
                db.add(EmailProcessado(
                    empresa_id=empresa_id, message_id=documento.identificador,
                    assunto=documento.assunto, remetente=documento.remetente,
                    recebido_em=documento.recebido_em,
                    status=StatusEmail.QUARENTENA.value, motivo=motivo,
                    anexos={"nomes": [a.nome for a in documento.anexos]}))
                savepoint.commit()
                db.commit()
                fonte.marcar_quarentena(documento, motivo)
                resumo.quarentena += 1
                continue

            houve_v01 = False
            for anexo in xmls:
                pdf = pdfs[0].conteudo if pdfs else None
                try:
                    _processar_xml(db, empresa, parametro, documento,
                                   anexo.conteudo, pdf,
                                   origem_da_fonte(fonte), resumo)
                except NFeParseError as exc:
                    oc = registrar_ocorrencia(
                        db, empresa_id, "V01", Severidade.BLOQUEANTE,
                        f"O arquivo {anexo.nome} não é uma NF-e válida: {exc}")
                    _conta_ocorrencias(resumo, [oc])
                    houve_v01 = True

            status = StatusEmail.QUARENTENA if houve_v01 else StatusEmail.PROCESSADO
            motivo = "XML inválido (V01)." if houve_v01 else None
            db.add(EmailProcessado(
                empresa_id=empresa_id, message_id=documento.identificador,
                assunto=documento.assunto, remetente=documento.remetente,
                recebido_em=documento.recebido_em, status=status.value, motivo=motivo,
                anexos={"nomes": [a.nome for a in documento.anexos]}))
            savepoint.commit()
            db.commit()
            if houve_v01:
                fonte.marcar_quarentena(documento, motivo or "")
                resumo.quarentena += 1
            else:
                fonte.marcar_processado(documento)
        except Exception as exc:  # noqa: BLE001 — falha isolada não derruba o lote
            savepoint.rollback()
            db.commit()
            resumo.erros.append(f"{documento.identificador}: {exc}")
            traceback.print_exc()

    # Relatório e e-mail — falha aqui não invalida o ciclo
    try:
        if resumo.notas_novas or resumo.duplicatas_descartadas or resumo.quarentena:
            from app.services import email_sender, relatorio
            caminho_pdf = relatorio.gerar_relatorio_ciclo(db, empresa, resumo, inicio)
            if parametro.emails_notificacao:
                email_sender.enviar_relatorio(parametro.emails_notificacao,
                                              empresa, resumo, inicio, caminho_pdf)
    except Exception as exc:  # noqa: BLE001
        resumo.erros.append(f"relatorio/email: {exc}")
        traceback.print_exc()

    execucao.terminado_em = datetime.now(timezone.utc)
    execucao.sucesso = not resumo.erros
    execucao.resumo = resumo.como_dict()
    db.commit()
    return resumo


def origem_da_fonte(fonte: FonteDeDocumentos) -> str:
    from app.fontes.pasta import FontePasta
    return "pasta" if isinstance(fonte, FontePasta) else "imap"


def fonte_configurada() -> FonteDeDocumentos:
    """Cria a fonte a partir das variáveis de ambiente."""
    if settings.FONTE_DOCUMENTOS == "imap":
        from app.fontes.imap import FonteImap
        return FonteImap(settings.IMAP_HOST, settings.IMAP_PORTA,
                         settings.IMAP_USUARIO, settings.IMAP_SENHA,
                         settings.IMAP_PASTA)
    from app.fontes.pasta import FontePasta
    return FontePasta(settings.PASTA_ENTRADA, settings.PASTA_PROCESSADOS,
                      settings.PASTA_QUARENTENA)
