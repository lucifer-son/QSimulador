"""Modelos de população finita M/M/1//N e M/M/c//N (regime estacionário).

N fontes alternam entre "pensar" (tempo médio Z, taxa λ = 1/Z por fonte) e
esperar/ser atendidas por c servidores de taxa μ. É o modelo do "reparador de
máquinas" e a descrição natural de um teste de carga com N usuários.

Processo de nascimento e morte com λₙ = (N − n)·λ e μₙ = min(n, c)·μ:

    pₙ ∝ C(N, n)·aⁿ                       para n ≤ c
    pₙ ∝ N!/((N − n)!·c!·cⁿ⁻ᶜ)·aⁿ          para n > c,     a = λ/μ

calculado em escala logarítmica (como `_stationary_distribution`). A capacidade
nunca limita (o sistema comporta no máximo N clientes), então não há bloqueio.
"""

import numpy as np
from scipy.special import gammaln

from app.domain.metrics.queue_metrics import QueueModelMetrics
from app.domain.validation.finite_population import validate_finite_population_parameters


def _distribution(a: float, servers: int, population: int) -> np.ndarray:
    n = np.arange(population + 1)
    log_terms = (
        gammaln(population + 1)
        - gammaln(population - n + 1)
        + n * np.log(a)
        - gammaln(np.minimum(n, servers) + 1)
        - np.maximum(n - servers, 0) * np.log(servers)
    )
    terms = np.exp(log_terms - log_terms.max())
    return terms / terms.sum()


def finite_population_metrics(
    mu: float, servers: int, population: int, think_time: float
) -> QueueModelMetrics:
    """M/M/c//N. `think_time` é Z, o tempo médio entre o fim de um atendimento e a próxima requisição.

    `throughput` é a vazão X = λ·(N − L). W e Wq valem para cada requisição (todas são aceitas) e
    `p_wait` é a probabilidade de uma requisição encontrar todos os servidores ocupados
    (pelo teorema da chegada, calculada sobre o sistema com N − 1 clientes).
    Vale W = N/X − Z (lei do tempo de resposta interativo).
    """
    mu, c, n_pop, z = validate_finite_population_parameters(mu, servers, population, think_time)

    if z == 0:
        # Limite Z → 0: os N clientes estão sempre no sistema.
        busy = min(n_pop, c)
        x = busy * mu
        lq = float(max(n_pop - c, 0))
        return QueueModelMetrics(
            rho=busy / c, L=float(n_pop), Lq=lq, W=n_pop / x, Wq=lq / x,
            p0=0.0, throughput=x, p_wait=1.0 if n_pop > c else 0.0, p_block=0.0,
        )

    lam_src = 1.0 / z
    p = _distribution(lam_src / mu, c, n_pop)
    n = np.arange(n_pop + 1)

    big_l = float(np.dot(n, p))
    x = lam_src * (n_pop - big_l)
    lq = float(np.dot(np.maximum(n - c, 0), p))
    busy = float(np.dot(np.minimum(n, c), p))

    # Distribuição vista por quem chega: proporcional a (N − n)·pₙ.
    seen = (n_pop - n) * p
    p_wait = float(seen[c:].sum() / seen.sum()) if seen.sum() > 0 else 0.0

    return QueueModelMetrics(
        rho=busy / c, L=big_l, Lq=lq, W=big_l / x, Wq=lq / x,
        p0=float(p[0]), throughput=x, p_wait=p_wait, p_block=0.0,
    )
