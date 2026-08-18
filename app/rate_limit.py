"""Limitador de tentativas de login em memória: N falhas seguidas para a
mesma chave (e-mail + IP) bloqueiam novas tentativas por um tempo."""
import time

MAX_TENTATIVAS = 5
JANELA_BLOQUEIO_SEGUNDOS = 300

_tentativas: dict[str, tuple[int, float]] = {}  # chave -> (falhas, bloqueado_ate)


def _chave(email: str, ip: str) -> str:
    return f"{email.strip().lower()}:{ip}"


def segundos_bloqueado(email: str, ip: str) -> float:
    """Segundos restantes de bloqueio para a chave, ou 0 se liberada."""
    _, bloqueado_ate = _tentativas.get(_chave(email, ip), (0, 0.0))
    return max(bloqueado_ate - time.monotonic(), 0.0)


def registra_falha(email: str, ip: str) -> None:
    chave = _chave(email, ip)
    falhas, _ = _tentativas.get(chave, (0, 0.0))
    falhas += 1
    bloqueado_ate = (time.monotonic() + JANELA_BLOQUEIO_SEGUNDOS
                     if falhas >= MAX_TENTATIVAS else 0.0)
    _tentativas[chave] = (falhas, bloqueado_ate)


def limpa(email: str, ip: str) -> None:
    _tentativas.pop(_chave(email, ip), None)
