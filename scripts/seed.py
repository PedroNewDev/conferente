"""Dados iniciais de demonstração.

Cria uma empresa, três usuários (um por papel), três fornecedores, doze
produtos com de-para e quatro pedidos de compra.
Idempotente: se a empresa já existe, não recria.
"""
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import Base, SessionLocal, engine
from app.models import (
    Empresa, Fornecedor, Parametro, PedidoCompra, PedidoItem,
    Produto, ProdutoFornecedor, Usuario,
)
from app.security import hash_senha

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


def popular(db) -> bool:
    """Insere os dados de demonstração na sessão dada. Devolve False se já existem."""
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
    return True


def rodar() -> None:
    Base.metadata.create_all(engine)
    db = SessionLocal()
    try:
        if popular(db):
            print("Seed concluído: 1 empresa, 3 usuários, 3 fornecedores, "
                  "12 produtos com de-para e 4 pedidos de compra.")
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
