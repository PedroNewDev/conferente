"""Modelos SQLAlchemy. Somente estrutura — nenhuma regra de negócio aqui."""
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CHAR,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# JSONB no Postgres, JSON comum nos demais bancos (SQLite nos testes)
TipoJson = JSON().with_variant(JSONB(), "postgresql")
# BIGSERIAL no Postgres; no SQLite o autoincremento exige INTEGER
TipoBigInt = BigInteger().with_variant(Integer(), "sqlite")


class Empresa(Base):
    __tablename__ = "empresa"

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    razao_social: Mapped[str] = mapped_column(String(200))
    cnpj: Mapped[str] = mapped_column(CHAR(14), unique=True)
    email_recebimento: Mapped[str | None] = mapped_column(String(200))
    ativa: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    parametro: Mapped["Parametro"] = relationship(back_populates="empresa", uselist=False)


class Parametro(Base):
    __tablename__ = "parametro"

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"), unique=True)
    tolerancia_preco_percentual: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.50"))
    tolerancia_valor_absoluto: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0.05"))
    tolerancia_quantidade_percentual: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal("0.00"))
    dias_alerta_vencimento: Mapped[int] = mapped_column(Integer, default=5)
    intervalo_ciclo_minutos: Mapped[int] = mapped_column(Integer, default=15)
    dias_max_emissao_retroativa: Mapped[int] = mapped_column(Integer, default=90)
    emails_notificacao: Mapped[str | None] = mapped_column(Text)  # separados por vírgula
    bloquear_sem_pedido: Mapped[bool] = mapped_column(Boolean, default=False)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    empresa: Mapped[Empresa] = relationship(back_populates="parametro")


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = (UniqueConstraint("empresa_id", "email"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    nome: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(200))
    senha_hash: Mapped[str] = mapped_column(String(255))
    papel: Mapped[str] = mapped_column(String(20))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Fornecedor(Base):
    __tablename__ = "fornecedor"
    __table_args__ = (UniqueConstraint("empresa_id", "cnpj"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    cnpj: Mapped[str] = mapped_column(CHAR(14))
    razao_social: Mapped[str] = mapped_column(String(200))
    nome_fantasia: Mapped[str | None] = mapped_column(String(200))
    uf: Mapped[str | None] = mapped_column(CHAR(2))
    municipio: Mapped[str | None] = mapped_column(String(120))
    email: Mapped[str | None] = mapped_column(String(200))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Produto(Base):
    __tablename__ = "produto"
    __table_args__ = (UniqueConstraint("empresa_id", "codigo_interno"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    codigo_interno: Mapped[str] = mapped_column(String(60))
    descricao: Mapped[str] = mapped_column(String(200))
    unidade: Mapped[str] = mapped_column(String(10))
    ncm: Mapped[str | None] = mapped_column(CHAR(8))
    estoque_atual: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    estoque_minimo: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    custo_medio: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProdutoFornecedor(Base):
    __tablename__ = "produto_fornecedor"
    __table_args__ = (UniqueConstraint("empresa_id", "fornecedor_id", "codigo_no_fornecedor"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"))
    fornecedor_id: Mapped[int] = mapped_column(ForeignKey("fornecedor.id"))
    codigo_no_fornecedor: Mapped[str] = mapped_column(String(60))
    ean: Mapped[str | None] = mapped_column(String(14))
    descricao_no_fornecedor: Mapped[str | None] = mapped_column(String(200))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    produto: Mapped[Produto] = relationship()


class PedidoCompra(Base):
    __tablename__ = "pedido_compra"
    __table_args__ = (UniqueConstraint("empresa_id", "numero"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    numero: Mapped[str] = mapped_column(String(30))
    fornecedor_id: Mapped[int] = mapped_column(ForeignKey("fornecedor.id"))
    data_emissao: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="aberto")
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    frete_previsto: Mapped[Decimal] = mapped_column(Numeric(15, 2), default=Decimal("0"))
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    itens: Mapped[list["PedidoItem"]] = relationship(back_populates="pedido")
    fornecedor: Mapped[Fornecedor] = relationship()


class PedidoItem(Base):
    __tablename__ = "pedido_item"

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    pedido_id: Mapped[int] = mapped_column(ForeignKey("pedido_compra.id"))
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    quantidade_atendida: Mapped[Decimal] = mapped_column(Numeric(15, 4), default=Decimal("0"))
    preco_unitario: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    pedido: Mapped[PedidoCompra] = relationship(back_populates="itens")
    produto: Mapped[Produto] = relationship()


class NotaFiscal(Base):
    __tablename__ = "nota_fiscal"
    __table_args__ = (
        UniqueConstraint("empresa_id", "chave"),
        Index("ix_nota_fiscal_empresa_status", "empresa_id", "status"),
        Index("ix_nota_fiscal_empresa_emissao", "empresa_id", "data_emissao"),
    )

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    chave: Mapped[str] = mapped_column(CHAR(44))
    numero: Mapped[int] = mapped_column(Integer)
    serie: Mapped[int] = mapped_column(Integer)
    modelo: Mapped[str] = mapped_column(CHAR(2))
    data_emissao: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    fornecedor_id: Mapped[int | None] = mapped_column(ForeignKey("fornecedor.id"))
    cnpj_emitente: Mapped[str] = mapped_column(CHAR(14))
    nome_emitente: Mapped[str | None] = mapped_column(String(200))
    cnpj_destinatario: Mapped[str | None] = mapped_column(CHAR(14))
    natureza_operacao: Mapped[str | None] = mapped_column(String(120))
    cfop_predominante: Mapped[str | None] = mapped_column(CHAR(4))
    tipo_operacao: Mapped[str] = mapped_column(String(20), default="compra")
    valor_produtos: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_desconto: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_frete: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_seguro: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_outros: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_ipi: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_st: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    status: Mapped[str] = mapped_column(String(20), default="recebida")
    pedido_id: Mapped[int | None] = mapped_column(ForeignKey("pedido_compra.id"))
    origem: Mapped[str] = mapped_column(String(20))
    email_message_id: Mapped[str | None] = mapped_column(String(300))
    xml_path: Mapped[str | None] = mapped_column(Text)
    pdf_path: Mapped[str | None] = mapped_column(Text)
    recebida_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processada_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    aprovada_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    justificativa_liberacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    itens: Mapped[list["NotaItem"]] = relationship(back_populates="nota")
    duplicatas: Mapped[list["Duplicata"]] = relationship(back_populates="nota")
    ocorrencias: Mapped[list["Ocorrencia"]] = relationship(back_populates="nota")
    fornecedor: Mapped[Fornecedor | None] = relationship()
    pedido: Mapped[PedidoCompra | None] = relationship()


class NotaItem(Base):
    __tablename__ = "nota_item"
    __table_args__ = (UniqueConstraint("nota_id", "n_item"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    nota_id: Mapped[int] = mapped_column(ForeignKey("nota_fiscal.id"))
    n_item: Mapped[int] = mapped_column(Integer)
    codigo_fornecedor: Mapped[str | None] = mapped_column(String(60))
    ean: Mapped[str | None] = mapped_column(String(14))
    descricao: Mapped[str | None] = mapped_column(String(200))
    ncm: Mapped[str | None] = mapped_column(CHAR(8))
    cfop: Mapped[str | None] = mapped_column(CHAR(4))
    unidade: Mapped[str | None] = mapped_column(String(10))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    valor_unitario: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    valor_total: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    numero_pedido_xml: Mapped[str | None] = mapped_column(String(30))
    item_pedido_xml: Mapped[int | None] = mapped_column(Integer)
    produto_id: Mapped[int | None] = mapped_column(ForeignKey("produto.id"))
    pedido_item_id: Mapped[int | None] = mapped_column(ForeignKey("pedido_item.id"))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    nota: Mapped[NotaFiscal] = relationship(back_populates="itens")
    produto: Mapped[Produto | None] = relationship()
    pedido_item: Mapped[PedidoItem | None] = relationship()


class Duplicata(Base):
    __tablename__ = "duplicata"

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    nota_id: Mapped[int] = mapped_column(ForeignKey("nota_fiscal.id"))
    numero: Mapped[str | None] = mapped_column(String(30))
    vencimento: Mapped[date] = mapped_column(Date)
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    nota: Mapped[NotaFiscal] = relationship(back_populates="duplicatas")


class Ocorrencia(Base):
    __tablename__ = "ocorrencia"
    __table_args__ = (Index("ix_ocorrencia_empresa_resolvida", "empresa_id", "resolvida"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    nota_id: Mapped[int | None] = mapped_column(ForeignKey("nota_fiscal.id"))
    nota_item_id: Mapped[int | None] = mapped_column(ForeignKey("nota_item.id"))
    tipo: Mapped[str] = mapped_column(String(40))
    severidade: Mapped[str] = mapped_column(String(20))
    mensagem: Mapped[str] = mapped_column(Text)
    detalhe: Mapped[dict | None] = mapped_column(TipoJson)
    valor_impacto: Mapped[Decimal | None] = mapped_column(Numeric(15, 2))
    resolvida: Mapped[bool] = mapped_column(Boolean, default=False)
    resolvida_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"))
    resolvida_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    observacao_resolucao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    nota: Mapped[NotaFiscal | None] = relationship(back_populates="ocorrencias")


class MovimentoEstoque(Base):
    __tablename__ = "movimento_estoque"
    __table_args__ = (Index("ix_movimento_empresa_produto", "empresa_id", "produto_id", "criado_em"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    produto_id: Mapped[int] = mapped_column(ForeignKey("produto.id"))
    tipo: Mapped[str] = mapped_column(String(20))
    quantidade: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    custo_unitario: Mapped[Decimal | None] = mapped_column(Numeric(15, 4))
    saldo_apos: Mapped[Decimal] = mapped_column(Numeric(15, 4))
    origem_tipo: Mapped[str] = mapped_column(String(20))
    origem_id: Mapped[int | None] = mapped_column(TipoBigInt)
    observacao: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    produto: Mapped[Produto] = relationship()


class ContaPagar(Base):
    __tablename__ = "conta_pagar"
    __table_args__ = (
        UniqueConstraint("nota_id", "numero_parcela"),
        Index("ix_conta_empresa_status_venc", "empresa_id", "status", "vencimento"),
    )

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    nota_id: Mapped[int] = mapped_column(ForeignKey("nota_fiscal.id"))
    numero_parcela: Mapped[int] = mapped_column(Integer)
    valor: Mapped[Decimal] = mapped_column(Numeric(15, 2))
    vencimento: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="aberta")
    pago_em: Mapped[date | None] = mapped_column(Date)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    nota: Mapped[NotaFiscal] = relationship()


class EmailProcessado(Base):
    __tablename__ = "email_processado"
    __table_args__ = (UniqueConstraint("empresa_id", "message_id"),)

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int] = mapped_column(ForeignKey("empresa.id"))
    message_id: Mapped[str] = mapped_column(String(300))
    assunto: Mapped[str | None] = mapped_column(String(300))
    remetente: Mapped[str | None] = mapped_column(String(200))
    recebido_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20))
    motivo: Mapped[str | None] = mapped_column(Text)
    anexos: Mapped[dict | None] = mapped_column(TipoJson)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ExecucaoJob(Base):
    __tablename__ = "execucao_job"

    id: Mapped[int] = mapped_column(TipoBigInt, primary_key=True, autoincrement=True)
    empresa_id: Mapped[int | None] = mapped_column(ForeignKey("empresa.id"))
    job: Mapped[str] = mapped_column(String(60))
    iniciado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    terminado_em: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sucesso: Mapped[bool | None] = mapped_column(Boolean)
    resumo: Mapped[dict | None] = mapped_column(TipoJson)
    erro: Mapped[str | None] = mapped_column(Text)
    criado_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
