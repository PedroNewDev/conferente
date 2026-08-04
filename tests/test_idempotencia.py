"""Reprocessar os mesmos documentos não pode duplicar nota, movimento nem conta."""
import shutil
from pathlib import Path

from app.models import ContaPagar, MovimentoEstoque, NotaFiscal
from app.services.pipeline import executar_ciclo
from scripts.gerar_notas_teste import gerar_todos


def _estado(db, empresa) -> tuple[int, int, int]:
    return (
        db.query(NotaFiscal).filter_by(empresa_id=empresa.id).count(),
        db.query(MovimentoEstoque).filter_by(empresa_id=empresa.id).count(),
        db.query(ContaPagar).filter_by(empresa_id=empresa.id).count(),
    )


def test_mesmo_arquivo_reenviado(db, empresa, fonte):
    """Mesmo conteúdo, mesmo nome: barrado pelo identificador do documento."""
    gerar_todos(Path(fonte.entrada))
    # guarda uma cópia para simular o reenvio
    backup = Path(fonte.entrada).parent / "backup"
    shutil.copytree(fonte.entrada, backup)

    executar_ciclo(db, empresa.id, fonte)
    antes = _estado(db, empresa)

    for arquivo in backup.iterdir():
        shutil.copy(arquivo, fonte.entrada / arquivo.name)
    resumo2 = executar_ciclo(db, empresa.id, fonte)

    assert resumo2.notas_novas == 0
    assert _estado(db, empresa) == antes


def test_mesma_nota_com_outro_nome(db, empresa, fonte):
    """Arquivo renomeado (identificador novo, chave igual): barrado pela V12."""
    gerar_todos(Path(fonte.entrada))
    backup = Path(fonte.entrada).parent / "backup"
    shutil.copytree(fonte.entrada, backup)

    executar_ciclo(db, empresa.id, fonte)
    antes = _estado(db, empresa)

    for arquivo in backup.iterdir():
        shutil.copy(arquivo, fonte.entrada / f"reenvio_{arquivo.name}")
    resumo2 = executar_ciclo(db, empresa.id, fonte)

    assert resumo2.notas_novas == 0
    # 14 XMLs interpretáveis: 13 notas + a cópia 06, todas barradas pela V12
    assert resumo2.duplicatas_descartadas == 14
    assert _estado(db, empresa) == antes
