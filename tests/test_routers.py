"""Testes de ponta a ponta das rotas HTML/POST: autenticação, CSRF,
isolamento por empresa e os fluxos de criação/edição principais."""
import re
from datetime import date, datetime, timezone

from app.enums import StatusConta
from app.models import ContaPagar, Fornecedor, NotaFiscal, Ocorrencia, Produto

EMAIL_COMPRADOR = "carlos@mercadobompreco.com.br"
SENHA_COMPRADOR = "compra123"
EMAIL_FINANCEIRO = "marina@mercadobompreco.com.br"
SENHA_FINANCEIRO = "financeiro123"


def login(client, email=EMAIL_COMPRADOR, senha=SENHA_COMPRADOR):
    return client.post("/login", data={"email": email, "senha": senha},
                       follow_redirects=False)


def csrf(client, url):
    r = client.get(url)
    m = re.search(r'name="csrf_token" value="([^"]+)"', r.text)
    assert m, f"csrf_token não encontrado em {url}"
    return m.group(1)


def test_login_credenciais_invalidas(client, empresa):
    r = login(client, senha="errada")
    assert r.status_code == 401
    assert "incorretos" in r.text


def test_login_ok_e_acesso_liberado(client, empresa):
    r = login(client)
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    r = client.get("/produtos")
    assert r.status_code == 200


def test_rota_protegida_sem_sessao_redireciona_ao_login(client, empresa):
    r = client.get("/produtos", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_post_sem_csrf_falha(client, empresa):
    login(client)
    r = client.post("/produtos", data={
        "codigo_interno": "NOVO-1", "descricao": "Produto novo", "unidade": "UN",
    })
    assert r.status_code == 422


def test_post_com_csrf_invalido_falha(client, empresa):
    login(client)
    r = client.post("/produtos", data={
        "codigo_interno": "NOVO-1", "descricao": "Produto novo", "unidade": "UN",
        "csrf_token": "token-invalido",
    })
    assert r.status_code == 403


def test_criar_produto_ok(client, db, empresa):
    login(client)
    token = csrf(client, "/produtos")
    r = client.post("/produtos", data={
        "codigo_interno": "NOVO-1", "descricao": "Produto novo", "unidade": "UN",
        "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    assert db.query(Produto).filter_by(codigo_interno="NOVO-1",
                                       empresa_id=empresa.id).first()


def test_criar_produto_duplicado_mostra_erro_amigavel(client, db, empresa):
    login(client)
    existente = db.query(Produto).filter_by(empresa_id=empresa.id).first()
    token = csrf(client, "/produtos")
    r = client.post("/produtos", data={
        "codigo_interno": existente.codigo_interno, "descricao": "Duplicado",
        "unidade": "UN", "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "erro=" in r.headers["location"]
    r = client.get(r.headers["location"])
    assert "já existe" in r.text.lower()


def test_criar_produto_estoque_minimo_invalido_mostra_erro_amigavel(client, empresa):
    login(client)
    token = csrf(client, "/produtos")
    r = client.post("/produtos", data={
        "codigo_interno": "NOVO-2", "descricao": "Produto novo", "unidade": "UN",
        "estoque_minimo": "não-é-numero", "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "erro=" in r.headers["location"]
    r = client.get(r.headers["location"])
    assert "inválido" in r.text.lower()


def test_pedido_com_data_invalida_mostra_erro_amigavel(client, db, empresa):
    login(client)
    fornecedor = db.query(Fornecedor).filter_by(empresa_id=empresa.id).first()
    token = csrf(client, "/pedidos")
    r = client.post("/pedidos", data={
        "numero": "PC-DATA-INVALIDA", "fornecedor_id": str(fornecedor.id),
        "data_emissao": "31-13-2026", "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "erro=" in r.headers["location"]
    r = client.get("/pedidos")
    assert "PC-DATA-INVALIDA" not in r.text


def test_criar_fornecedor_cnpj_invalido(client, empresa):
    login(client)
    token = csrf(client, "/fornecedores")
    r = client.post("/fornecedores", data={
        "cnpj": "11111111111111", "razao_social": "Invalido LTDA",
        "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    assert "erro=" in r.headers["location"]


def test_pedido_com_fornecedor_de_outra_empresa_eh_rejeitado(client, db, empresa):
    from app.models import Empresa, Parametro

    outra = Empresa(razao_social="Outra Empresa LTDA", cnpj="11444777000161")
    db.add(outra)
    db.flush()
    db.add(Parametro(empresa_id=outra.id))
    forn_outra = Fornecedor(empresa_id=outra.id, cnpj="34028316000103",
                            razao_social="Fornecedor de outra empresa")
    db.add(forn_outra)
    db.commit()

    login(client)
    token = csrf(client, "/pedidos")
    r = client.post("/pedidos", data={
        "numero": "PC-CROSS", "fornecedor_id": str(forn_outra.id),
        "data_emissao": "2026-01-01", "csrf_token": token,
    }, follow_redirects=False)
    # rota lança 404 (fornecedor não encontrado nesta empresa); o handler
    # global de 404 redireciona ao painel
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    r = client.get("/pedidos")
    assert "PC-CROSS" not in r.text


def test_criar_pedido_adicionar_item_e_cancelar(client, db, empresa):
    login(client)
    fornecedor = db.query(Fornecedor).filter_by(empresa_id=empresa.id).first()
    produto = db.query(Produto).filter_by(empresa_id=empresa.id).first()

    token = csrf(client, "/pedidos")
    r = client.post("/pedidos", data={
        "numero": "PC-NOVO", "fornecedor_id": str(fornecedor.id),
        "data_emissao": "2026-01-01", "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    pedido_url = r.headers["location"]

    token = csrf(client, pedido_url)
    r = client.post(f"{pedido_url}/itens", data={
        "produto_id": str(produto.id), "quantidade": "10",
        "preco_unitario": "5.00", "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303

    token = csrf(client, pedido_url)
    r = client.post(f"{pedido_url}/cancelar", data={"csrf_token": token},
                    follow_redirects=False)
    assert r.status_code == 303
    r = client.get(pedido_url)
    assert "cancelado" in r.text.lower()


def test_ajuste_de_estoque(client, db, empresa):
    login(client)
    produto = db.query(Produto).filter_by(empresa_id=empresa.id).first()
    url = f"/estoque/{produto.id}/movimentos"
    token = csrf(client, url)
    r = client.post(f"/estoque/{produto.id}/ajuste", data={
        "novo_saldo": "42", "justificativa": "Contagem manual de teste",
        "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    db.refresh(produto)
    assert float(produto.estoque_atual) == 42


def test_resolver_ocorrencia(client, db, empresa):
    login(client)
    oc = Ocorrencia(empresa_id=empresa.id, tipo="C02", severidade="alerta",
                    mensagem="Ocorrência de teste")
    db.add(oc)
    db.commit()

    token = csrf(client, "/ocorrencias")
    r = client.post(f"/ocorrencias/{oc.id}/resolver", data={
        "observacao": "Resolvida no teste", "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    db.refresh(oc)
    assert oc.resolvida is True


def test_pagar_conta(client, db, empresa):
    login(client, EMAIL_FINANCEIRO, SENHA_FINANCEIRO)
    nota = NotaFiscal(empresa_id=empresa.id, chave="1" * 44, numero=1, serie=1,
                      modelo="55", data_emissao=datetime.now(timezone.utc),
                      cnpj_emitente="11444777000161", origem="teste",
                      tipo_operacao="compra", status="aprovada",
                      nome_emitente="Fornecedor Teste", valor_total="100.00")
    db.add(nota)
    db.flush()
    conta = ContaPagar(empresa_id=empresa.id, nota_id=nota.id, numero_parcela=1,
                       valor="100.00", vencimento=date(2026, 1, 10),
                       status=StatusConta.ABERTA.value)
    db.add(conta)
    db.commit()

    token = csrf(client, "/financeiro/contas")
    r = client.post(f"/financeiro/contas/{conta.id}/pagar", data={
        "csrf_token": token,
    }, follow_redirects=False)
    assert r.status_code == 303
    db.refresh(conta)
    assert conta.status == StatusConta.PAGA.value


def test_logout_exige_post_com_csrf(client, empresa):
    login(client)
    r = client.get("/logout")
    assert r.status_code == 405

    token = csrf(client, "/")
    r = client.post("/logout", data={"csrf_token": token}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"

    r = client.get("/produtos", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
