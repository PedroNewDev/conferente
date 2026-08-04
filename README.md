# Conferente

Mini-SaaS de compras, estoque e contas a pagar cujo núcleo é uma rotina
automática que **recebe notas fiscais eletrônicas, valida, concilia com o
pedido de compra, classifica divergências e aplica os efeitos no estoque e no
financeiro** — sem intervenção humana. Toda decisão é determinística: o XML
já vem estruturado, e o resto é aritmética e comparação com o cadastro.

## Stack

Python 3.11+ · FastAPI · Jinja2 (server-side) · SQLAlchemy 2 · Alembic ·
PostgreSQL 15 · lxml · imap-tools · WeasyPrint · APScheduler · pytest ·
Docker Compose.

## Demonstração no ar

**https://conferente-neon.vercel.app** — login `ana@mercadobompreco.com.br` / `admin123`.

Esse ambiente roda em plataforma serverless, que **não tem disco persistente**.
Por isso o modo de demonstração (`api/index.py`) usa SQLite em `/tmp`: o banco
é criado e semeado no primeiro acesso de cada instância, já com os 15 XMLs de
teste na pasta de entrada — cada visitante encontra um ambiente limpo e pode
rodar o ciclo do zero. O agendador fica desligado (não há processo de fundo em
serverless); o ciclo é disparado pelo botão do painel.

O **ambiente oficial** é o `docker-compose.yml` abaixo: PostgreSQL, disco
persistente, agendador ativo a cada 15 minutos e relatório em PDF.

## Como rodar (Docker — recomendado)

```bash
cp .env.example .env
docker compose up --build
```

O container aplica as migrações, roda o seed e sobe em
**http://localhost:8000**. Login de demonstração:

| Usuário | Senha | Papel |
|---|---|---|
| `ana@mercadobompreco.com.br` | `admin123` | admin |
| `carlos@mercadobompreco.com.br` | `compra123` | comprador |

## Como rodar sem Docker (desenvolvimento)

```bash
python -m venv .venv
.venv/Scripts/activate            # Windows  (Linux: source .venv/bin/activate)
pip install -r requirements.txt
# .env mínimo para desenvolvimento local com SQLite:
#   APP_SECRET=chave-dev-local
#   DATABASE_URL=sqlite:///./conferente.db
#   AGENDADOR_ATIVO=false
alembic upgrade head
python scripts/seed.py
uvicorn app.main:app --reload
```

> Sem Docker o banco pode ser SQLite (a suíte de testes usa SQLite em
> memória). O ambiente oficial é PostgreSQL via Docker Compose.
> No Windows sem as bibliotecas GTK, o relatório do ciclo sai em HTML em vez
> de PDF — no Docker sai sempre em PDF (WeasyPrint).

## Roteiro de demonstração (5 minutos)

1. **Gerar as notas de teste** — 15 cenários, um por arquivo:
   ```bash
   python scripts/gerar_notas_teste.py --saida ./entrada/novos --cenario todos
   ```
2. Entrar no sistema e abrir o **Painel**.
3. Clicar em **“▶ Executar ciclo agora”**. A rotina lê a pasta de entrada,
   valida, concilia e lança tudo em segundos.
4. Conferir o resultado:
   - **Notas fiscais** — 7 aprovadas, 3 bloqueadas, 3 rejeitadas,
     1 duplicata descartada, 1 XML corrompido em quarentena;
   - **Divergências** — fila com P02 (preço acima), P04 (quantidade acima),
     P06 (item fora do pedido) e o **impacto financeiro em reais**;
   - **Estoque** — saldos atualizados e custo médio recalculado;
   - **Contas a pagar** — parcelas criadas a partir das duplicatas;
   - `relatorios/` — relatório do ciclo (as três seções + impacto no rodapé).
5. Abrir a nota bloqueada por preço, **liberar com justificativa** e mostrar
   que os efeitos foram aplicados e o autor ficou registrado.
6. Rodar o ciclo de novo e mostrar que **nada duplica** (idempotência).
7. `GET /docs` — documentação automática da API JSON.

## Fonte de documentos

O pipeline não sabe de onde o XML veio — a fonte é abstrata:

- `FONTE_DOCUMENTOS=pasta` (padrão): lê `entrada/novos/`, move para
  `entrada/processados/AAAA-MM/` ou `entrada/quarentena/`.
- `FONTE_DOCUMENTOS=imap`: lê a caixa `INBOX` via IMAP (mensagens não lidas
  com anexo), move para as pastas `Processados`/`Quarentena` da própria
  caixa. Configure `IMAP_*` no `.env` (no Gmail, use senha de aplicativo).

## Catálogo de regras

- **V01–V12** — validação estrutural e fiscal (DV da chave, CNPJs,
  destinatário, somas, datas, duplicidade). Bloqueante rejeita a nota.
- **C01–C03** — cadastro (fornecedor desconhecido criado inativo, item sem
  de-para, NCM fora do formato).
- **P01–P09** — conciliação com o pedido (preço, quantidade, item fora do
  pedido, entrega parcial, frete, CFOP). P02/P04 calculam o **impacto
  financeiro** que o relatório soma.

Severidades, fórmulas e decisões de interpretação: `DECISOES.md`.

## Testes

```bash
pytest             # 51 testes: unitários, um por regra, integração,
                   # idempotência e isolamento multiempresa
```

O teste de integração roda o ciclo completo sobre os 15 XMLs do gerador e
confere status, ocorrências, estoque, custo médio e contas — exatamente o
resultado esperado de cada cenário.

## Fora de escopo (evolução prevista)

Este projeto **não consulta a SEFAZ** para confirmar autorização ou
cancelamento das notas — a validação é estrutural e de negócio. A consulta ao
web service da SEFAZ (com certificado digital A1) é a evolução natural do
produto, junto com a manifestação do destinatário. Também ficam fora:
emissão de documentos fiscais, apuração de impostos, integração com ERP e
conciliação bancária.
