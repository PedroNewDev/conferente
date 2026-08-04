"""Exportação das notas conferidas em JSON, para importação em outro sistema.

O Conferente faz a entrada da nota — leitura do XML, validação e conciliação
com o pedido — e entrega o lançamento pronto para o ERP principal consumir.

Todo valor numérico sai como texto: JSON não tem tipo decimal, e converter
para float perderia precisão em dinheiro. Quem importa deve ler como decimal.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.enums import Severidade
from app.models import Empresa, NotaFiscal
from app.services.explicacoes import explicar

VERSAO_LAYOUT = "1.0"


def _texto(valor) -> str | None:
    return None if valor is None else str(valor)


def item_para_dict(item) -> dict:
    """Um item da nota com o produto já resolvido pelo de-para."""
    return {
        "numero_item": item.n_item,
        "codigo_no_fornecedor": item.codigo_fornecedor,
        "codigo_interno": item.produto.codigo_interno if item.produto else None,
        "descricao": item.descricao,
        "descricao_interna": item.produto.descricao if item.produto else None,
        "ean": item.ean,
        "ncm": item.ncm,
        "cfop": item.cfop,
        "unidade": item.unidade,
        "quantidade": _texto(item.quantidade),
        "valor_unitario": _texto(item.valor_unitario),
        "valor_total": _texto(item.valor_total),
        "identificado": item.produto_id is not None,
        "pedido": {
            "quantidade": _texto(item.pedido_item.quantidade),
            "preco_unitario": _texto(item.pedido_item.preco_unitario),
        } if item.pedido_item else None,
    }


def nota_para_dict(nota: NotaFiscal) -> dict:
    """A nota inteira no formato de importação."""
    divergencias = [
        {
            "codigo": oc.tipo,
            "descricao": explicar(oc.tipo),
            "severidade": oc.severidade,
            "valor_impacto": _texto(oc.valor_impacto),
            "resolvida": oc.resolvida,
        }
        for oc in nota.ocorrencias
        if oc.severidade != Severidade.INFORMATIVA.value
    ]
    return {
        "chave_acesso": nota.chave,
        "numero": nota.numero,
        "serie": nota.serie,
        "modelo": nota.modelo,
        "data_emissao": nota.data_emissao.isoformat(),
        "natureza_operacao": nota.natureza_operacao,
        "tipo_operacao": nota.tipo_operacao,
        "cfop_predominante": nota.cfop_predominante,
        "fornecedor": {
            "cnpj": nota.cnpj_emitente,
            "razao_social": nota.nome_emitente,
            "cadastrado": bool(nota.fornecedor and nota.fornecedor.ativo),
        },
        "pedido_compra": nota.pedido.numero if nota.pedido else None,
        "totais": {
            "produtos": _texto(nota.valor_produtos),
            "desconto": _texto(nota.valor_desconto),
            "frete": _texto(nota.valor_frete),
            "seguro": _texto(nota.valor_seguro),
            "outros": _texto(nota.valor_outros),
            "ipi": _texto(nota.valor_ipi),
            "st": _texto(nota.valor_st),
            "total": _texto(nota.valor_total),
        },
        "itens": [item_para_dict(i) for i in sorted(nota.itens, key=lambda i: i.n_item)],
        "parcelas": [
            {
                "numero": d.numero,
                "vencimento": d.vencimento.isoformat(),
                "valor": _texto(d.valor),
            }
            for d in nota.duplicatas
        ],
        "conferencia": {
            "status": nota.status,
            "movimenta_estoque": (nota.status == "aprovada"
                                  and nota.tipo_operacao == "compra"),
            "divergencias": divergencias,
        },
    }


def montar_pacote(empresa: Empresa, notas: list[NotaFiscal]) -> dict:
    """Envelope do arquivo: identifica a origem e o layout para quem importa."""
    return {
        "layout": "conferente-nfe",
        "versao": VERSAO_LAYOUT,
        "gerado_em": datetime.now(timezone.utc).isoformat(),
        "observacao": ("Valores numéricos são texto para preservar a precisão "
                       "decimal; leia-os como decimal, não como float."),
        "empresa": {"cnpj": empresa.cnpj, "razao_social": empresa.razao_social},
        "quantidade_notas": len(notas),
        "notas": [nota_para_dict(n) for n in notas],
    }


def notas_para_exportar(db: Session, empresa_id: int,
                        status: str | None = "aprovada") -> list[NotaFiscal]:
    """Por padrão só o que passou na conferência — é o que o ERP deve receber."""
    consulta = db.query(NotaFiscal).filter(NotaFiscal.empresa_id == empresa_id)
    if status:
        consulta = consulta.filter(NotaFiscal.status == status)
    return consulta.order_by(NotaFiscal.data_emissao).all()
