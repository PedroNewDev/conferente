"""Executa um ciclo de recebimento manualmente, pela linha de comando."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal
from app.models import Empresa
from app.services.pipeline import executar_ciclo, fonte_configurada


def main() -> None:
    db = SessionLocal()
    try:
        empresas = db.query(Empresa).filter_by(ativa=True).all()
        if not empresas:
            print("Nenhuma empresa ativa. Rode scripts/seed.py primeiro.")
            return
        for empresa in empresas:
            print(f"== Ciclo para {empresa.razao_social} ==")
            resumo = executar_ciclo(db, empresa.id, fonte_configurada())
            for chave, valor in resumo.como_dict().items():
                print(f"  {chave}: {valor}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
