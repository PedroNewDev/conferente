"""Modelos Pydantic de saída da API JSON.

As telas HTML usam formulários tradicionais validados por `Form(...)`;
estes esquemas documentam o contrato da API em `/docs`.
"""
from pydantic import BaseModel


class NotaResumo(BaseModel):
    id: int
    chave: str
    numero: int
    fornecedor: str | None
    status: str
    valor_total: str


class ItemNota(BaseModel):
    n_item: int
    descricao: str | None
    quantidade: str
    valor_unitario: str
    valor_total: str


class OcorrenciaSaida(BaseModel):
    tipo: str
    severidade: str
    mensagem: str
    valor_impacto: str | None
    resolvida: bool


class NotaDetalhe(NotaResumo):
    serie: int
    tipo_operacao: str
    itens: list[ItemNota]
    ocorrencias: list[OcorrenciaSaida]


class PosicaoEstoque(BaseModel):
    codigo: str
    descricao: str
    estoque_atual: str
    estoque_minimo: str
    custo_medio: str


class Indicadores(BaseModel):
    notas_hoje: int
    aprovadas_hoje: int
    notas_bloqueadas: int
    impacto_em_aberto: str
    contas_em_aberto: str
