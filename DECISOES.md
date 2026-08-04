# Decisões de projeto

Pontos em que havia mais de uma leitura possível do requisito. Em cada um,
a escolha foi pela interpretação mais conservadora — a que erra para o lado
de segurar a nota em vez de deixar passar.

## 1. Status final de uma nota que só tem alertas

Uma nota cujo emitente não está cadastrado (C01) ou cujo item não tem de-para
(C02) passa por todas as validações sem nenhum impedimento.

**Decisão:** termina como `aprovada`, carregando as ocorrências. `validada` é
um estado intermediário do processamento, não um estado final — do contrário
a nota ficaria parada sem que ninguém tivesse motivo para agir sobre ela.
O efeito prático continua conservador: item sem de-para não movimenta estoque.

## 2. P06 e itens sem de-para

P06 acusa item presente na nota e ausente no pedido.

**Dúvida:** um item sem de-para não tem produto resolvido, então nunca casa
com um item do pedido. Se P06 valesse para ele, todo item não cadastrado
bloquearia a nota inteira.

**Decisão:** a comparação com o pedido considera apenas itens com produto
identificado. Item sem de-para gera C02 (alerta), fica fora do comparativo e
não movimenta estoque — o comprador vê a pendência e resolve o cadastro.

## 3. P09 e operações que não são compra

P09 acusa CFOP predominante fora da faixa de venda (5xxx/6xxx/7xxx).

**Dúvida:** uma devolução (CFOP 5202) começa com 5, então não dispara P09
pela letra da regra — mas também não é compra.

**Decisão:** P09 dispara apenas quando o CFOP está fora da faixa. Operações
classificadas como devolução, remessa ou bonificação recebem uma ocorrência
informativa própria, deixando explícito que foram registradas sem efeito no
estoque ou no financeiro.

## 4. Conciliação de operações que não são compra

**Decisão:** as regras P01 a P08 só rodam quando `tipo_operacao == compra`.
Conciliar uma devolução contra um pedido de compra não faz sentido de
negócio, e apenas a compra gera efeito patrimonial.

## 5. Geração do PDF fora do Docker

O relatório é montado em HTML e convertido por WeasyPrint, que depende de
bibliotecas nativas nem sempre presentes fora do container.

**Decisão:** no Docker o relatório sai em PDF. Sem as bibliotecas nativas, o
mesmo HTML é gravado em disco. O conteúdo é idêntico e nenhum ciclo falha por
causa do conversor — perder o relatório inteiro por um problema de
formatação seria pior do que entregá-lo em outro formato.

## 6. Identidade do documento no envio manual

**Decisão:** o upload pela tela usa a mesma esteira do ciclo automático, e a
proteção contra duplicidade continua sendo a chave de acesso (V12). O
identificador do documento inclui usuário e nome do arquivo apenas para
rastrear a origem.
