"""Tradução dos códigos do catálogo de regras para linguagem comum.

A tela do automatizador não mostra "P02 bloqueante" — mostra "cobraram mais
caro que o combinado". O código técnico continua gravado na ocorrência e
aparece no sistema completo.
"""

EXPLICACOES: dict[str, str] = {
    # Validação fiscal
    "V01": "O arquivo não é uma nota fiscal válida",
    "V02": "A chave da nota foi adulterada",
    "V03": "Os dados da nota não batem com a chave",
    "V04": "O CNPJ do fornecedor é inválido",
    "V05": "O CNPJ do destinatário é inválido",
    "V06": "Esta nota foi emitida para outra empresa",
    "V07": "A soma dos itens não bate com o total",
    "V08": "As contas da nota não fecham",
    "V09": "As parcelas não somam o total da nota",
    "V10": "A data de emissão está no futuro",
    "V11": "Nota emitida há muito tempo",
    "V12": "Nota repetida — já tinha sido recebida antes",
    # Cadastro
    "C01": "Fornecedor ainda não cadastrado",
    "C02": "Produto sem vínculo com o seu cadastro",
    "C03": "Código NCM fora do padrão",
    # Conciliação com o pedido
    "P01": "Não há pedido de compra correspondente",
    "P02": "Cobraram mais caro que o combinado",
    "P03": "Cobraram mais barato que o combinado",
    "P04": "Entregaram mais do que foi pedido",
    "P05": "Entrega parcial do pedido",
    "P06": "Item que não estava no pedido",
    "P07": "Item do pedido não veio nesta entrega",
    "P08": "Frete acima do previsto no pedido",
    "P09": "Operação que não é uma compra",
    "P09-INFO": "Registrada sem efeito no estoque ou no financeiro",
    # Financeiro
    "F01": "Nota sem parcelas — prazo de 30 dias assumido",
    "CANCELAMENTO": "Nota cancelada manualmente",
}


def explicar(tipo: str) -> str:
    """Devolve a frase em linguagem comum para o código da regra."""
    return EXPLICACOES.get(tipo, tipo)
