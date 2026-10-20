"""Modelo analítico Erlang-B (M/M/c/c): sistema de perda, sem fila (Fase 10).

Chegadas de Poisson (λ), c servidores de taxa μ e nenhum lugar de espera: quem chega e encontra
os c servidores ocupados é perdido. Com a = λ/μ (tráfego oferecido, em Erlangs):

    B(0, a) = 1;  B(n, a) = a·B(n−1, a) / (n + a·B(n−1, a))        (recursão estável, sem fatoriais)

O bloqueio B(c, a) vale para qualquer distribuição de serviço (insensibilidade de Erlang), então a
fórmula não muda no M/G/c/c. Medidas: tráfego carregado a·(1 − B), utilização por servidor
a·(1 − B)/c, vazão λ·(1 − B) e W = 1/μ (não há espera: Lq = Wq = 0).
"""

from dataclasses import asdict, dataclass

import numpy as np
from scipy.special import gammaln, logsumexp

from app.analytical.mmck import erlang_b
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.mmck import MAX_SERVERS, validate_servers
from app.domain.validation.numbers import validate_positive_finite


@dataclass(frozen=True)
class ErlangBMetrics:
    offered_load: float   # a = λ/μ, em Erlangs
    carried_load: float   # a·(1 − B): servidores ocupados em média
    lost_rate: float      # λ·B: chegadas perdidas por unidade de tempo
    rho: float            # utilização por servidor
    L: float              # clientes no sistema (= tráfego carregado)
    Lq: float             # sempre 0
    W: float              # 1/μ
    Wq: float             # sempre 0
    p0: float             # probabilidade de todos os servidores livres
    throughput: float     # λ·(1 − B)
    p_wait: float         # sempre 0
    p_block: float        # B(c, a)

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def validate_erlangb_parameters(lam: object, mu: object, servers: object) -> tuple[float, float, int]:
    return validate_positive_finite("λ", lam), validate_positive_finite("μ", mu), validate_servers(servers)


def _p0(a: float, servers: int) -> float:
    n = np.arange(servers + 1)
    return float(np.exp(-logsumexp(n * np.log(a) - gammaln(n + 1))))


def erlangb_metrics(lam: float, mu: float, servers: int) -> ErlangBMetrics:
    """Métricas do Erlang-B. Sempre estável (a perda limita o sistema)."""
    lam, mu, c = validate_erlangb_parameters(lam, mu, servers)
    a = lam / mu
    b = erlang_b(a, c)
    carried = a * (1 - b)
    return ErlangBMetrics(
        offered_load=a, carried_load=carried, lost_rate=lam * b, rho=carried / c, L=carried,
        Lq=0.0, W=1 / mu, Wq=0.0, p0=_p0(a, c), throughput=lam * (1 - b), p_wait=0.0, p_block=b,
    )


@dataclass(frozen=True)
class ErlangBSizing:
    target_blocking: float
    servers: int                  # menor c com B(c, a) ≤ alvo
    blocking: float               # B(c, a)
    blocking_previous: float | None   # B(c − 1, a); None se c = 1
    offered_load: float
    carried_load: float
    rho: float
    lost_rate: float

    def as_dict(self) -> dict:
        return asdict(self)


def validate_target_blocking(target: object) -> float:
    value = validate_positive_finite("target_blocking", target)
    if value >= 1:
        raise QueueValidationError("target_blocking deve ser menor que 1 (é uma probabilidade).", "target_blocking")
    return value


def erlangb_size(lam: float, mu: float, target_blocking: float) -> ErlangBSizing:
    """Menor número de servidores que mantém o bloqueio em no máximo `target_blocking`.

    B(c, a) é decrescente em c, então a busca para no primeiro c que atende. Levanta erro se nem
    MAX_SERVERS servidores bastam.
    """
    lam = validate_positive_finite("λ", lam)
    mu = validate_positive_finite("μ", mu)
    target = validate_target_blocking(target_blocking)
    a = lam / mu
    b, previous = 1.0, None
    for c in range(1, MAX_SERVERS + 1):
        previous_b = b
        b = a * b / (c + a * b)
        if b <= target:
            carried = a * (1 - b)
            return ErlangBSizing(
                target_blocking=target, servers=c, blocking=b,
                blocking_previous=None if c == 1 else previous_b,
                offered_load=a, carried_load=carried, rho=carried / c, lost_rate=lam * b,
            )
    raise QueueValidationError(
        f"Nem {MAX_SERVERS} servidores atingem o bloqueio de {target:g} com {a:.6g} Erlangs de tráfego.",
        "target_blocking",
    )
