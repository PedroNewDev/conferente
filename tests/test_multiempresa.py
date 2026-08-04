"""Isolamento por empresa: a mesma chave pode existir nas duas, e nenhuma
enxerga os dados da outra."""
from pathlib import Path

from app.models import Empresa, NotaFiscal, Parametro
from app.services.pipeline import executar_ciclo
from app.fontes.pasta import FontePasta
from scripts.gerar_notas_teste import gerar_todos


def test_mesma_chave_em_duas_empresas(db, empresa, tmp_path):
    empresa2 = Empresa(razao_social="Filial Dois LTDA", cnpj="11444777000161")
    db.add(empresa2)
    db.flush()
    db.add(Parametro(empresa_id=empresa2.id))
    db.commit()

    nota1 = db.query(NotaFiscal).filter_by(empresa_id=empresa.id).first()
    assert nota1 is None  # banco limpo

    # processa os mesmos arquivos para as duas empresas
    for i, emp in enumerate((empresa, empresa2)):
        fonte = FontePasta(str(tmp_path / f"novos{i}"), str(tmp_path / f"proc{i}"),
                           str(tmp_path / f"quar{i}"))
        gerar_todos(Path(fonte.entrada))
        executar_ciclo(db, emp.id, fonte)

    notas1 = db.query(NotaFiscal).filter_by(empresa_id=empresa.id).all()
    notas2 = db.query(NotaFiscal).filter_by(empresa_id=empresa2.id).all()

    # as duas empresas conseguiram registrar as mesmas chaves
    chaves1 = {n.chave for n in notas1}
    chaves2 = {n.chave for n in notas2}
    assert chaves1 == chaves2
    assert len(notas1) == len(notas2) == 13

    # nenhuma nota de uma empresa aparece na consulta da outra
    ids1 = {n.id for n in notas1}
    ids2 = {n.id for n in notas2}
    assert ids1.isdisjoint(ids2)
