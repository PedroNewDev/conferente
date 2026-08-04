"""Interface abstrata das fontes de documentos.

O pipeline não sabe se o XML veio de uma pasta ou de uma caixa de e-mail —
trocar a origem é trocar uma variável de ambiente.
"""
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Iterable, Protocol


@dataclass
class Anexo:
    nome: str
    conteudo: bytes
    tipo: str  # "xml" | "pdf" | "outro"


@dataclass
class Documento:
    identificador: str  # Message-ID ou caminho do arquivo
    assunto: str | None
    remetente: str | None
    recebido_em: datetime
    anexos: list[Anexo] = field(default_factory=list)


class FonteDeDocumentos(Protocol):
    def listar_novos(self) -> Iterable[Documento]: ...
    def marcar_processado(self, documento: Documento) -> None: ...
    def marcar_quarentena(self, documento: Documento, motivo: str) -> None: ...


def classificar_anexo(nome: str, conteudo: bytes) -> str:
    """Classifica por extensão e conteúdo. XML só é 'xml' se for de NF-e."""
    nome_baixo = nome.lower()
    if nome_baixo.endswith(".xml") and b"portalfiscal.inf.br/nfe" in conteudo:
        return "xml"
    if nome_baixo.endswith(".pdf"):
        return "pdf"
    return "outro"


def expandir_anexos(nome: str, conteudo: bytes) -> list[Anexo]:
    """Devolve os anexos de um arquivo; ZIPs são descompactados em memória."""
    if nome.lower().endswith(".zip"):
        anexos: list[Anexo] = []
        try:
            with zipfile.ZipFile(BytesIO(conteudo)) as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    dados = zf.read(info)
                    anexos.append(Anexo(nome=info.filename, conteudo=dados,
                                        tipo=classificar_anexo(info.filename, dados)))
        except zipfile.BadZipFile:
            anexos.append(Anexo(nome=nome, conteudo=conteudo, tipo="outro"))
        return anexos
    return [Anexo(nome=nome, conteudo=conteudo, tipo=classificar_anexo(nome, conteudo))]
