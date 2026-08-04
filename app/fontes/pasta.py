"""Fonte de documentos em pasta local — usada em desenvolvimento e nos testes.

O identificador é o nome do arquivo + SHA-256 do conteúdo, o que mantém a
idempotência mesmo se o arquivo for renomeado.
"""
import hashlib
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from app.fontes.base import Documento, expandir_anexos


class FontePasta:
    def __init__(self, entrada: str, processados: str, quarentena: str) -> None:
        self.entrada = Path(entrada)
        self.processados = Path(processados)
        self.quarentena = Path(quarentena)
        for pasta in (self.entrada, self.processados, self.quarentena):
            pasta.mkdir(parents=True, exist_ok=True)
        # guarda o caminho original de cada documento listado neste ciclo
        self._caminhos: dict[str, Path] = {}

    def listar_novos(self) -> Iterable[Documento]:
        for arquivo in sorted(self.entrada.iterdir()):
            if not arquivo.is_file():
                continue
            conteudo = arquivo.read_bytes()
            digest = hashlib.sha256(conteudo).hexdigest()
            identificador = f"{arquivo.name}:{digest}"
            self._caminhos[identificador] = arquivo
            yield Documento(
                identificador=identificador,
                assunto=arquivo.name,
                remetente=None,
                recebido_em=datetime.fromtimestamp(arquivo.stat().st_mtime,
                                                   tz=timezone.utc),
                anexos=expandir_anexos(arquivo.name, conteudo),
            )

    def marcar_processado(self, documento: Documento) -> None:
        origem = self._caminhos.get(documento.identificador)
        if origem is None or not origem.exists():
            return
        destino = self.processados / datetime.now().strftime("%Y-%m")
        destino.mkdir(parents=True, exist_ok=True)
        shutil.move(str(origem), str(destino / origem.name))

    def marcar_quarentena(self, documento: Documento, motivo: str) -> None:
        origem = self._caminhos.get(documento.identificador)
        if origem is None or not origem.exists():
            return
        shutil.move(str(origem), str(self.quarentena / origem.name))
        (self.quarentena / f"{origem.name}.motivo.txt").write_text(motivo,
                                                                   encoding="utf-8")
