"""Fonte de documentos via IMAP — usada em produção (M11).

Busca mensagens não lidas com anexo na INBOX. O identificador é o Message-ID.
As pastas `Processados` e `Quarentena` são criadas se não existirem.
"""
from datetime import datetime, timezone
from typing import Iterable

from imap_tools import AND, MailBox

from app.fontes.base import Documento, expandir_anexos


class FonteImap:
    def __init__(self, host: str, porta: int, usuario: str, senha: str,
                 pasta: str = "INBOX") -> None:
        self.host = host
        self.porta = porta
        self.usuario = usuario
        self.senha = senha
        self.pasta = pasta
        self._uids: dict[str, str] = {}  # identificador -> uid da mensagem

    def _conectar(self) -> MailBox:
        caixa = MailBox(self.host, self.porta)
        caixa.login(self.usuario, self.senha, initial_folder=self.pasta)
        return caixa

    def _garantir_pasta(self, caixa: MailBox, nome: str) -> None:
        if not caixa.folder.exists(nome):
            caixa.folder.create(nome)

    def listar_novos(self) -> Iterable[Documento]:
        with self._conectar() as caixa:
            for msg in caixa.fetch(AND(seen=False), mark_seen=False):
                anexos = []
                for att in msg.attachments:
                    anexos.extend(expandir_anexos(att.filename or "anexo",
                                                  att.payload))
                if not anexos:
                    continue
                identificador = msg.headers.get("message-id", (msg.uid,))[0].strip() \
                    if msg.headers.get("message-id") else str(msg.uid)
                self._uids[identificador] = msg.uid
                yield Documento(
                    identificador=identificador,
                    assunto=msg.subject,
                    remetente=msg.from_,
                    recebido_em=msg.date or datetime.now(timezone.utc),
                    anexos=anexos,
                )

    def _mover(self, documento: Documento, destino: str) -> None:
        uid = self._uids.get(documento.identificador)
        if uid is None:
            return
        with self._conectar() as caixa:
            self._garantir_pasta(caixa, destino)
            caixa.flag(uid, ["\\Seen"], True)
            caixa.move(uid, destino)

    def marcar_processado(self, documento: Documento) -> None:
        self._mover(documento, "Processados")

    def marcar_quarentena(self, documento: Documento, motivo: str) -> None:
        self._mover(documento, "Quarentena")
