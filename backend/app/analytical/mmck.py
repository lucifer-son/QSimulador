"""Modelos analíticos M/M/c, M/M/1/K e M/M/c/K (regime estacionário).

- M/M/c: c servidores, fila ilimitada. Usa a fórmula de Erlang C, calculada a
  partir da recursão de Erlang B (estável numericamente, sem fatoriais).
- Capacidade finita K (M/M/1/K e M/M/c/K): resolve a distribuição estacionária
  do processo de nascimento e morte, em escala logarítmica para evitar
  overflow, e deriva as métricas dela.
"""

import numpy as np
from scipy.special import gammaln

from app.domain.metrics.queue_metrics import QueueModelMetrics
from app.domain.validation.mmck import (
    validate_mmc_parameters,
    validate_mmck_parameters,
    validate_queue_parameters,
)


def erlang_b(offered_load: float, servers: int) -> float:
    """Probabilidade de bloqueio de Erlang B, B(c, a), por recursão estável."""
    b = 1.0
    for k in range(1, servers + 1):
        b = offered_load * b / (k + offered_load * b)
    return b


def mmc_metrics(lam: float, mu: float, servers: int) -> QueueModelMetrics:
    """M/M/c com fila ilimitada. Exige λ < c·μ."""
    lam, mu, c = validate_mmc_parameters(lam, mu, servers)

    a = lam / mu                      # carga oferecida (em Erlangs)
    rho = a / c                       # utilização por servidor
    b = erlang_b(a, c)
    p_wait = b / (1 - rho * (1 - b))  # Erlang C

    Lq = p_wait * rho / (1 - rho)
    Wq = Lq / lam
    return QueueModelMetrics(
        rho=rho,
        L=Lq + a,
        Lq=Lq,
        W=Wq + 1 / mu,
        Wq=Wq,
        throughput=lam,
        p_wait=p_wait,
        p_block=0.0,
    )


def _stationary_distribution(lam: float, mu: float, servers: int, capacity: int) -> np.ndarray:
    """p_0..p_K do processo de nascimento e morte (taxa de morte min(n, c)·μ)."""
    n = np.arange(capacity + 1)
    # log de a^n / (c! · c^(n−c)) para n > c, e de a^n / n! para n ≤ c
    log_terms = (
        n * np.log(lam / mu)
        - gammaln(np.minimum(n, servers) + 1)
        - np.maximum(n - servers, 0) * np.log(servers)
    )
    terms = np.exp(log_terms - log_terms.max())
    return terms / terms.sum()


def mmck_metrics(lam: float, mu: float, servers: int, capacity: int) -> QueueModelMetrics:
    """M/M/c/K: `capacity` é a capacidade total (fila + atendimento). Sempre estável."""
    lam, mu, c, k = validate_mmck_parameters(lam, mu, servers, capacity)

    p = _stationary_distribution(lam, mu, c, k)
    n = np.arange(k + 1)

    p_block = float(p[k])
    lam_eff = lam * (1 - p_block)
    L = float(np.dot(n, p))
    Lq = float(np.dot(np.maximum(n - c, 0), p))
    busy_servers = float(np.dot(np.minimum(n, c), p))
    p_wait = float(p[c:k].sum()) / (1 - p_block) if k > c else 0.0

    return QueueModelMetrics(
        rho=busy_servers / c,
        L=L,
        Lq=Lq,
        W=L / lam_eff,
        Wq=Lq / lam_eff,
        throughput=lam_eff,
        p_wait=p_wait,
        p_block=p_block,
    )


def mm1k_metrics(lam: float, mu: float, capacity: int) -> QueueModelMetrics:
    """M/M/1/K: um servidor e capacidade total K."""
    return mmck_metrics(lam, mu, 1, capacity)


def queue_metrics(
    lam: float, mu: float, servers: int, capacity: int | None
) -> QueueModelMetrics:
    """Escolhe o modelo pelo par (servers, capacity); capacity=None é M/M/c."""
    validate_queue_parameters(lam, mu, servers, capacity)
    if capacity is None:
        return mmc_metrics(lam, mu, servers)
    return mmck_metrics(lam, mu, servers, capacity)
