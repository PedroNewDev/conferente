"""Contas a pagar geradas a partir das notas aprovadas."""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.enums import Severidade, StatusConta
from app.models import ContaPagar, NotaFiscal
from app.services.validacao import registrar_ocorrencia
from app.utils.tempo import hoje


def gerar_contas_a_pagar(db: Session, nota: NotaFiscal) -> list[ContaPagar]:
    """Cada duplicata vira uma parcela. Sem duplicatas, cria parcela única com
    vencimento em emissão + 30 dias e registra que o prazo foi arbitrado."""
    contas: list[ContaPagar] = []
    if nota.duplicatas:
        for n, dup in enumerate(nota.duplicatas, start=1):
            contas.append(ContaPagar(
                empresa_id=nota.empresa_id, nota_id=nota.id, numero_parcela=n,
                valor=dup.valor, vencimento=dup.vencimento,
            ))
    else:
        vencimento = nota.data_emissao.date() + timedelta(days=30)
        contas.append(ContaPagar(
            empresa_id=nota.empresa_id, nota_id=nota.id, numero_parcela=1,
            valor=Decimal(nota.valor_total or 0), vencimento=vencimento,
        ))
        registrar_ocorrencia(
            db, nota.empresa_id, "F01", Severidade.INFORMATIVA,
            "Nota sem duplicatas: criada conta única com vencimento arbitrado "
            f"em 30 dias ({vencimento.isoformat()}).",
            nota=nota)
    db.add_all(contas)
    db.flush()
    return contas


def contas_a_vencer(db: Session, empresa_id: int, dias: int) -> list[ContaPagar]:
    limite = hoje() + timedelta(days=dias)
    return (db.query(ContaPagar)
            .filter(ContaPagar.empresa_id == empresa_id,
                    ContaPagar.status == StatusConta.ABERTA.value,
                    ContaPagar.vencimento <= limite)
            .order_by(ContaPagar.vencimento)
            .all())


def marcar_paga(db: Session, empresa_id: int, conta_id: int,
                data_pagamento: date) -> ContaPagar:
    conta = (db.query(ContaPagar)
             .filter_by(id=conta_id, empresa_id=empresa_id)
             .one())
    conta.status = StatusConta.PAGA.value
    conta.pago_em = data_pagamento
    db.flush()
    return conta
