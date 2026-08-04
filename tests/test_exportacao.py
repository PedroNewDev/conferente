"""Exportação para outro sistema: o que sai no JSON e o que fica de fora."""
import json
from decimal import Decimal
from pathlib import Path

from app.models import Empresa, NotaFiscal
from app.services.exportacao import montar_pacote, nota_para_dict, notas_para_exportar
from app.services.pipeline import executar_ciclo
from scripts.gerar_notas_teste import gerar_todos


def _ciclo(db, empresa, fonte):
    gerar_todos(Path(fonte.entrada))
    executar_ciclo(db, empresa.id, fonte)


def test_exporta_apenas_aprovadas(db, empresa, fonte):
    _ciclo(db, empresa, fonte)
    notas = notas_para_exportar(db, empresa.id)
    assert notas, "deveria haver notas aprovadas"
    assert {n.status for n in notas} == {"aprovada"}

    # bloqueadas e rejeitadas não podem virar lançamento em outro sistema
    numeros = {n.numero for n in notas}
    assert 90002 not in numeros   # bloqueada por preço
    assert 90007 not in numeros   # rejeitada por chave adulterada


def test_conteudo_do_pacote(db, empresa, fonte):
    _ciclo(db, empresa, fonte)
    pacote = montar_pacote(empresa, notas_para_exportar(db, empresa.id))

    assert pacote["layout"] == "conferente-nfe"
    assert pacote["empresa"]["cnpj"] == empresa.cnpj
    assert pacote["quantidade_notas"] == len(pacote["notas"])

    # o pacote precisa sobreviver a json.dumps — é isso que o ERP recebe
    texto = json.dumps(pacote, ensure_ascii=False)
    assert json.loads(texto)["quantidade_notas"] == pacote["quantidade_notas"]


def test_item_traz_codigo_interno_e_do_fornecedor(db, empresa, fonte):
    _ciclo(db, empresa, fonte)
    nota = (db.query(NotaFiscal)
            .filter_by(empresa_id=empresa.id, numero=90001).one())
    dados = nota_para_dict(nota)

    assert dados["pedido_compra"] == "PC-1001"
    assert dados["conferencia"]["status"] == "aprovada"
    assert dados["conferencia"]["movimenta_estoque"] is True

    item = dados["itens"][0]
    assert item["codigo_no_fornecedor"] == "ALF001"     # como veio na nota
    assert item["codigo_interno"] == "ARZ-5"            # como está no cadastro
    assert item["identificado"] is True
    assert item["quantidade"] == "50.0000"
    assert item["valor_unitario"] == "22.5000"
    assert item["pedido"]["preco_unitario"] == "22.5000"

    # parcelas conferem com o total da nota
    soma = sum(Decimal(p["valor"]) for p in dados["parcelas"])
    assert soma == Decimal(dados["totais"]["total"])


def test_valores_saem_como_texto(db, empresa, fonte):
    """JSON não tem decimal; float perderia precisão em dinheiro."""
    _ciclo(db, empresa, fonte)
    dados = nota_para_dict(
        db.query(NotaFiscal).filter_by(empresa_id=empresa.id, numero=90001).one())
    assert isinstance(dados["totais"]["total"], str)
    assert isinstance(dados["itens"][0]["quantidade"], str)
    # e continuam exatos ao voltar para Decimal
    assert Decimal(dados["itens"][0]["valor_total"]) == Decimal("1125.00")


def test_item_sem_depara_vai_marcado(db, empresa, fonte):
    """O ERP precisa saber que o produto não foi identificado."""
    _ciclo(db, empresa, fonte)
    nota = (db.query(NotaFiscal)
            .filter_by(empresa_id=empresa.id, numero=90015).one())
    item = nota_para_dict(nota)["itens"][0]
    assert item["identificado"] is False
    assert item["codigo_interno"] is None
    assert item["codigo_no_fornecedor"] == "GAM-XYZ"


def test_devolucao_nao_movimenta_estoque(db, empresa, fonte):
    _ciclo(db, empresa, fonte)
    nota = (db.query(NotaFiscal)
            .filter_by(empresa_id=empresa.id, numero=90012).one())
    dados = nota_para_dict(nota)
    assert dados["tipo_operacao"] == "devolucao"
    assert dados["conferencia"]["movimenta_estoque"] is False


def test_exportacao_isolada_por_empresa(db, empresa, fonte):
    from app.models import Parametro
    outra = Empresa(razao_social="Outra Empresa LTDA", cnpj="34028316000103")
    db.add(outra)
    db.flush()
    db.add(Parametro(empresa_id=outra.id))
    db.commit()

    _ciclo(db, empresa, fonte)
    assert notas_para_exportar(db, outra.id) == []
