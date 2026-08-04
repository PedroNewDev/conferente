"""Movimentos de estoque e custo médio ponderado.

Toda alteração de saldo passa por um movimento — nunca por UPDATE direto em
`produto.estoque_atual`. O campo `saldo_apos` permite auditar a linha do tempo.
"""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session

from app.enums import TipoMovimento
from app.models import MovimentoEstoque, Produto

QUATRO = Decimal("0.0001")


def _trava_produto(db: Session, empresa_id: int, produto_id: int) -> Produto:
    """Carrega o produto com trava de linha, para evitar corrida entre o ciclo
    automático e um ajuste manual. No SQLite (testes) o with_for_update é inócuo."""
    produto = (db.query(Produto)
               .filter_by(id=produto_id, empresa_id=empresa_id)
               .with_for_update()
               .one())
    return produto


def registrar_entrada(db: Session, empresa_id: int, produto_id: int,
                      quantidade: Decimal, custo_unitario: Decimal,
                      origem_id: int | None) -> MovimentoEstoque:
    """Entrada por nota fiscal. Recalcula o custo médio ponderado."""
    produto = _trava_produto(db, empresa_id, produto_id)
    estoque_atual = Decimal(produto.estoque_atual)
    custo_medio = Decimal(produto.custo_medio)

    novo_saldo = estoque_atual + quantidade
    if novo_saldo != 0:
        novo_custo = ((estoque_atual * custo_medio + quantidade * custo_unitario)
                      / novo_saldo).quantize(QUATRO, rounding=ROUND_HALF_UP)
    else:
        novo_custo = custo_medio  # entrada que zera o saldo: mantém o custo anterior

    produto.estoque_atual = novo_saldo
    produto.custo_medio = novo_custo

    movimento = MovimentoEstoque(
        empresa_id=empresa_id, produto_id=produto_id,
        tipo=TipoMovimento.ENTRADA.value, quantidade=quantidade,
        custo_unitario=custo_unitario, saldo_apos=novo_saldo,
        origem_tipo="nota", origem_id=origem_id,
    )
    db.add(movimento)
    db.flush()
    return movimento


def registrar_saida(db: Session, empresa_id: int, produto_id: int,
                    quantidade: Decimal, origem_tipo: str,
                    origem_id: int | None) -> MovimentoEstoque:
    produto = _trava_produto(db, empresa_id, produto_id)
    novo_saldo = Decimal(produto.estoque_atual) - quantidade
    produto.estoque_atual = novo_saldo

    movimento = MovimentoEstoque(
        empresa_id=empresa_id, produto_id=produto_id,
        tipo=TipoMovimento.SAIDA.value, quantidade=quantidade,
        saldo_apos=novo_saldo, origem_tipo=origem_tipo, origem_id=origem_id,
    )
    db.add(movimento)
    db.flush()
    return movimento


def registrar_ajuste(db: Session, empresa_id: int, produto_id: int,
                     novo_saldo: Decimal, usuario_id: int,
                     observacao: str) -> MovimentoEstoque:
    """Ajuste manual: grava a diferença entre o saldo atual e o informado."""
    produto = _trava_produto(db, empresa_id, produto_id)
    diferenca = novo_saldo - Decimal(produto.estoque_atual)
    produto.estoque_atual = novo_saldo

    movimento = MovimentoEstoque(
        empresa_id=empresa_id, produto_id=produto_id,
        tipo=TipoMovimento.AJUSTE.value, quantidade=diferenca,
        saldo_apos=novo_saldo, origem_tipo="usuario", origem_id=usuario_id,
        observacao=observacao,
    )
    db.add(movimento)
    db.flush()
    return movimento


def produtos_abaixo_do_minimo(db: Session, empresa_id: int) -> list[Produto]:
    return (db.query(Produto)
            .filter(Produto.empresa_id == empresa_id,
                    Produto.ativo.is_(True),
                    Produto.estoque_atual < Produto.estoque_minimo)
            .order_by(Produto.descricao)
            .all())
