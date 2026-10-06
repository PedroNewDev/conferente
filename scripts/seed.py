"""Dados iniciais de demonstração.

Cria uma empresa, três usuários (um por papel), três fornecedores, doze
produtos com de-para e quatro pedidos de compra.
Idempotente: se a empresa já existe, não recria.
"""
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine
from app.fontes.pasta import FontePasta
from app.models import (
    Empresa, Fornecedor, Parametro, PedidoCompra, PedidoItem,
    Produto, ProdutoFornecedor, Usuario,
)
from app.security import hash_senha
from app.services.pipeline import executar_ciclo
from scripts.gerar_notas_teste import _it, montar_nota

FUSO_SP = timezone(timedelta(hours=-3))

# CNPJs com dígito verificador válido
CNPJ_EMPRESA = "11222333000181"
CNPJ_FORN_A = "11444777000161"     # Distribuidora Alfa
CNPJ_FORN_B = "34028316000103"     # Comercial Beta
CNPJ_FORN_C = "60701190000104"     # Indústria Gama

PRODUTOS = [
    # (código, descrição, unidade, ncm, mínimo, custo)
    ("ARZ-5", "Arroz branco tipo 1 5kg", "FD", "10063021", "20", "22.50"),
    ("FEJ-1", "Feijão carioca 1kg", "FD", "07133399", "30", "7.80"),
    ("ACU-2", "Açúcar cristal 2kg", "FD", "17019900", "25", "9.40"),
    ("OLE-900", "Óleo de soja 900ml", "CX", "15071000", "40", "6.90"),
    ("CAF-500", "Café torrado e moído 500g", "CX", "09012100", "15", "14.20"),
    ("MAC-500", "Macarrão espaguete 500g", "FD", "19021900", "35", "3.60"),
    ("LEI-1", "Leite integral UHT 1L", "CX", "04012010", "60", "4.85"),
    ("FAR-1", "Farinha de trigo 1kg", "FD", "11010010", "20", "4.30"),
    ("SAL-1", "Sal refinado 1kg", "FD", "25010020", "10", "1.95"),
    ("MOL-340", "Molho de tomate 340g", "CX", "21032010", "30", "2.40"),
    ("BIS-400", "Biscoito cream cracker 400g", "CX", "19053100", "25", "4.10"),
    ("DET-500", "Detergente neutro 500ml", "CX", "34022000", "45", "2.15"),
]


def popular(db, com_notas_demo: bool = False) -> bool:
    """Insere os dados de demonstração na sessão dada. Devolve False se já existem.

    `com_notas_demo=True` também simula o recebimento de 3 NF-e reais (uma
    aprovada, uma bloqueada, uma com entrega parcial), para a demonstração
    abrir com notas, estoque e contas a pagar já populados. Desligado por
    padrão porque os testes usam esta função esperando os pedidos "limpos"
    (sem entregas), e cada cenário de teste gera suas próprias notas."""
    if db.query(Empresa).filter_by(cnpj=CNPJ_EMPRESA).first():
        return False

    empresa = Empresa(
        razao_social="Mercado Bom Preço LTDA",
        cnpj=CNPJ_EMPRESA,
        email_recebimento="nfe@mercadobompreco.com.br",
    )
    db.add(empresa)
    db.flush()

    db.add(Parametro(empresa_id=empresa.id,
                     emails_notificacao="compras@mercadobompreco.com.br"))

    db.add_all([
        Usuario(empresa_id=empresa.id, nome="Ana Souza",
                email="ana@mercadobompreco.com.br",
                senha_hash=hash_senha("admin123"), papel="admin"),
        Usuario(empresa_id=empresa.id, nome="Carlos Lima",
                email="carlos@mercadobompreco.com.br",
                senha_hash=hash_senha("compra123"), papel="comprador"),
        Usuario(empresa_id=empresa.id, nome="Marina Duarte",
                email="marina@mercadobompreco.com.br",
                senha_hash=hash_senha("financeiro123"), papel="financeiro"),
    ])

    forn_a = Fornecedor(empresa_id=empresa.id, cnpj=CNPJ_FORN_A,
                        razao_social="Distribuidora Alfa de Alimentos LTDA",
                        nome_fantasia="Alfa Alimentos", uf="SP", municipio="São Paulo",
                        email="vendas@alfaalimentos.com.br")
    forn_b = Fornecedor(empresa_id=empresa.id, cnpj=CNPJ_FORN_B,
                        razao_social="Comercial Beta Distribuição S.A.",
                        nome_fantasia="Beta Distribuição", uf="SP", municipio="Campinas",
                        email="pedidos@betadist.com.br")
    forn_c = Fornecedor(empresa_id=empresa.id, cnpj=CNPJ_FORN_C,
                        razao_social="Indústria Gama de Produtos de Limpeza LTDA",
                        nome_fantasia="Gama Limpeza", uf="MG", municipio="Uberlândia",
                        email="comercial@gamalimpeza.com.br")
    db.add_all([forn_a, forn_b, forn_c])
    db.flush()

    produtos: list[Produto] = []
    for codigo, descricao, unidade, ncm, minimo, custo in PRODUTOS:
        p = Produto(empresa_id=empresa.id, codigo_interno=codigo,
                    descricao=descricao, unidade=unidade, ncm=ncm,
                    estoque_atual=Decimal("0"),
                    estoque_minimo=Decimal(minimo), custo_medio=Decimal(custo))
        produtos.append(p)
    db.add_all(produtos)
    db.flush()

    # De-para: Alfa fornece os 6 primeiros, Beta os 6 seguintes,
    # Gama fornece o detergente com código próprio também.
    for i, p in enumerate(produtos[:6]):
        db.add(ProdutoFornecedor(empresa_id=empresa.id, produto_id=p.id,
                                 fornecedor_id=forn_a.id,
                                 codigo_no_fornecedor=f"ALF{i + 1:03d}",
                                 descricao_no_fornecedor=p.descricao))
    for i, p in enumerate(produtos[6:]):
        db.add(ProdutoFornecedor(empresa_id=empresa.id, produto_id=p.id,
                                 fornecedor_id=forn_b.id,
                                 codigo_no_fornecedor=f"BET{i + 1:03d}",
                                 descricao_no_fornecedor=p.descricao))
    db.add(ProdutoFornecedor(empresa_id=empresa.id, produto_id=produtos[11].id,
                             fornecedor_id=forn_c.id,
                             codigo_no_fornecedor="GAM-DET500",
                             descricao_no_fornecedor="Detergente neutro Gama 500ml"))

    hoje = date.today()

    def cria_pedido(numero: str, fornecedor: Fornecedor, dias: int,
                    itens: list[tuple[Produto, str, str]],
                    frete: str = "0") -> None:
        """itens: lista de (produto, quantidade, preço unitário)."""
        pedido = PedidoCompra(empresa_id=empresa.id, numero=numero,
                              fornecedor_id=fornecedor.id,
                              data_emissao=hoje - timedelta(days=dias),
                              frete_previsto=Decimal(frete))
        db.add(pedido)
        db.flush()
        total = Decimal("0")
        for produto, qtd, preco in itens:
            q, pu = Decimal(qtd), Decimal(preco)
            vt = (q * pu).quantize(Decimal("0.01"))
            total += vt
            db.add(PedidoItem(pedido_id=pedido.id, produto_id=produto.id,
                              quantidade=q, preco_unitario=pu, valor_total=vt))
        pedido.valor_total = total

    cria_pedido("PC-1001", forn_a, 7, [
        (produtos[0], "50", "22.50"),
        (produtos[1], "80", "7.80"),
        (produtos[2], "60", "9.40"),
    ], frete="120.00")
    cria_pedido("PC-1002", forn_a, 5, [
        (produtos[3], "100", "6.90"),
        (produtos[4], "40", "14.20"),
    ])
    cria_pedido("PC-1003", forn_b, 4, [
        (produtos[6], "120", "4.85"),
        (produtos[7], "50", "4.30"),
        (produtos[9], "80", "2.40"),
    ], frete="80.00")
    cria_pedido("PC-1004", forn_b, 2, [
        (produtos[10], "60", "4.10"),
        (produtos[11], "90", "2.15"),
    ])

    db.commit()
    if com_notas_demo:
        _semear_notas_demo(db, empresa, forn_a, forn_b)
    return True


def _semear_notas_demo(db, empresa: Empresa, forn_a: Fornecedor, forn_b: Fornecedor) -> None:
    """Simula o recebimento de 3 NF-e reais via pipeline, para a demonstração
    já abrir com notas, estoque e contas a pagar — não só cadastros vazios.
    Cobre os três desfechos possíveis: aprovada, bloqueada e entrega parcial."""
    ontem = (datetime.now(FUSO_SP) - timedelta(days=1)).replace(microsecond=0)
    D = Decimal

    # 01 — bate exatamente com o pedido PC-1001: aprovada, fecha o pedido,
    # entra no estoque e gera contas a pagar.
    vprod_1001 = D("22.50") * 50 + D("7.80") * 80 + D("9.40") * 60
    vnf_1001 = vprod_1001 + D("120.00")
    nota1 = montar_nota(90101, (forn_a.cnpj, forn_a.razao_social), [
        _it("ALF001", "Arroz branco tipo 1 5kg", "10063021", "50", "22.50",
            xped="PC-1001", nitemped=1),
        _it("ALF002", "Feijao carioca 1kg", "07133399", "80", "7.80",
            xped="PC-1001", nitemped=2),
        _it("ALF003", "Acucar cristal 2kg", "17019900", "60", "9.40",
            xped="PC-1001", nitemped=3),
    ], ontem, frete=D("120.00"),
        duplicatas=[("001", vnf_1001 / 2), ("002", vnf_1001 / 2)])

    # 02 — preço do óleo 8% acima do pedido PC-1002: fica bloqueada, com
    # impacto financeiro calculado automaticamente.
    nota2 = montar_nota(90102, (forn_a.cnpj, forn_a.razao_social), [
        _it("ALF004", "Oleo de soja 900ml", "15071000", "100", "7.45",
            unidade="CX", xped="PC-1002"),
        _it("ALF005", "Cafe torrado e moido 500g", "09012100", "40", "14.20",
            unidade="CX", xped="PC-1002"),
    ], ontem - timedelta(days=1), duplicatas=[("001", D("1313.00"))])

    # 05 — entrega parcial (metade) do pedido PC-1004: aprovada, pedido fica
    # com status "parcial".
    nota3 = montar_nota(90103, (forn_b.cnpj, forn_b.razao_social), [
        _it("BET005", "Biscoito cream cracker 400g", "19053100", "30", "4.10",
            unidade="CX", xped="PC-1004"),
        _it("BET006", "Detergente neutro 500ml", "34022000", "45", "2.15",
            unidade="CX", xped="PC-1004"),
    ], ontem - timedelta(days=2), duplicatas=[("001", D("219.75"))])

    pasta_tmp = Path(tempfile.mkdtemp(prefix="conferente_seed_"))
    try:
        entrada = pasta_tmp / "entrada"
        entrada.mkdir()
        (entrada / "90101.xml").write_bytes(nota1)
        (entrada / "90102.xml").write_bytes(nota2)
        (entrada / "90103.xml").write_bytes(nota3)
        fonte = FontePasta(str(entrada), str(pasta_tmp / "processados"),
                           str(pasta_tmp / "quarentena"))
        executar_ciclo(db, empresa.id, fonte)
    finally:
        shutil.rmtree(pasta_tmp, ignore_errors=True)


def rodar() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if popular(db, com_notas_demo=True):
            print("Seed concluído: 1 empresa, 3 usuários, 3 fornecedores, "
                  "12 produtos com de-para, 4 pedidos de compra e 3 notas "
                  "já recebidas (aprovada, bloqueada, parcial).")
            print("Logins:")
            print("  ana@mercadobompreco.com.br     / admin123       (admin)")
            print("  carlos@mercadobompreco.com.br  / compra123      (comprador)")
            print("  marina@mercadobompreco.com.br  / financeiro123  (financeiro)")
        else:
            print("Seed já executado — empresa existente. Nada a fazer.")
    finally:
        db.close()


if __name__ == "__main__":
    rodar()
