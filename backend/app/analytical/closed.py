"""Modelo analítico fechado M/M/c//N (população finita; M/M/1//N quando c = 1).

N usuários alternam entre *pensar* (tempo exponencial de média Z, taxa λ = 1/Z por
usuário) e *pedir* um serviço (c servidores, tempo exponencial de taxa μ cada, fila
FIFO). É o modelo adequado para um teste de carga com N usuários simultâneos, como o
do JMeter, em que cada usuário só envia o próximo pedido depois de receber a resposta.

É um processo de nascimento e morte com taxa de chegada (N − n)·λ e de saída
min(n, c)·μ no estado n. A distribuição estacionária é calculada em escala
logarítmica (sem fatoriais), para N grande não estourar.
"""

import numpy as np
from scipy.special import logsumexp

from app.domain.metrics.queue_metrics import ClosedMetrics
from app.domain.validation.closed import validate_closed_parameters


def closed_distribution(users: int, think_time: float, mu: float, servers: int = 1) -> np.ndarray:
    """Distribuição estacionária p_n (n = 0..N) do número de usuários no sistema."""
    lam = 1.0 / think_time
    k = np.arange(users)
    log_ratio = np.log(users - k) + np.log(lam / mu) - np.log(np.minimum(k + 1, servers))
    log_w = np.concatenate(([0.0], np.cumsum(log_ratio)))
    return np.exp(log_w - logsumexp(log_w))


def closed_metrics(users: int, think_time: float, mu: float, servers: int = 1) -> ClosedMetrics:
    """Métricas do M/M/c//N em regime estacionário (`think_time` = Z, `mu` por servidor)."""
    n_users, z, mu_v, c = validate_closed_parameters(users, think_time, mu, servers)
    p = closed_distribution(n_users, z, mu_v, c)
    n = np.arange(n_users + 1)
    throughput = float(np.sum((n_users - n) * p) / z)
    L = float(np.sum(n * p))
    Lq = float(np.sum(np.maximum(n - c, 0) * p))
    return ClosedMetrics(
        rho=float(np.sum(np.minimum(n, c) * p) / c),
        L=L,
        Lq=Lq,
        W=L / throughput,
        Wq=Lq / throughput,
        p0=float(p[0]),
        throughput=throughput,
    )
