"""Relatório do ciclo: HTML (Jinja2) convertido em PDF pelo WeasyPrint.

Em máquinas sem as bibliotecas nativas do WeasyPrint (GTK no Windows), o
relatório é salvo como HTML — documentado no README. No Docker sai em PDF.
"""
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from sqlalchemy.orm import Session

from app.enums import StatusEmail, StatusNota
from app.models import EmailProcessado, Empresa, NotaFiscal

_env = Environment(
    loader=FileSystemLoader(Path(__file__).resolve().parent.parent / "templates"),
    autoescape=True,
)


def gerar_relatorio_ciclo(db: Session, empresa: Empresa, resumo, inicio: datetime) -> Path:
    """Monta o HTML do relatório e converte para PDF. Devolve o caminho gerado."""
    notas = []
    if resumo.notas_ids:
        notas = (db.query(NotaFiscal)
                 .filter(NotaFiscal.empresa_id == empresa.id,
                         NotaFiscal.id.in_(resumo.notas_ids))
                 .all())
    aprovadas = [n for n in notas if n.status == StatusNota.APROVADA.value]
    bloqueadas = [n for n in notas if n.status == StatusNota.BLOQUEADA.value]
    rejeitadas = [n for n in notas if n.status == StatusNota.REJEITADA.value]
    quarentena = (db.query(EmailProcessado)
                  .filter(EmailProcessado.empresa_id == empresa.id,
                          EmailProcessado.status == StatusEmail.QUARENTENA.value,
                          EmailProcessado.criado_em >= inicio)
                  .all())

    html = _env.get_template("relatorio_pdf.html").render(
        empresa=empresa, resumo=resumo, inicio=inicio,
        agora=datetime.now(), aprovadas=aprovadas,
        bloqueadas=bloqueadas, rejeitadas=rejeitadas, quarentena=quarentena,
    )

    pasta = Path("./relatorios")
    pasta.mkdir(parents=True, exist_ok=True)
    base = pasta / f"ciclo_{inicio.strftime('%Y%m%d_%H%M%S')}"

    try:
        from weasyprint import HTML  # import tardio: depende de libs nativas
        caminho = base.with_suffix(".pdf")
        HTML(string=html).write_pdf(str(caminho))
    except (ImportError, OSError):
        caminho = base.with_suffix(".html")
        caminho.write_text(html, encoding="utf-8")
    return caminho
