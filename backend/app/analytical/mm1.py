"""Modelo analítico M/M/1 (regime estacionário).

Chegadas de Poisson (taxa λ), serviço exponencial (taxa μ), um servidor,
fila ilimitada e disciplina FIFO. Requer λ < μ.
"""

from app.domain.metrics.queue_metrics import QueueMetrics
from app.domain.validation.mm1 import validate_mm1_parameters


def mm1_metrics(lam: float, mu: float) -> QueueMetrics:
    """Calcula ρ, L, Lq, W e Wq para um M/M/1.

    `lam` é a taxa média de chegada (λ) e `mu` a taxa média de serviço (μ),
    na mesma unidade (por exemplo, req/s). Os tempos saem na unidade inversa.

    Levanta QueueValidationError para parâmetros inválidos e
    UnstableSystemError quando λ >= μ.
    """
    lam, mu = validate_mm1_parameters(lam, mu)

    rho = lam / mu
    L = lam / (mu - lam)
    Lq = lam**2 / (mu * (mu - lam))
    W = 1 / (mu - lam)
    Wq = lam / (mu * (mu - lam))

    return QueueMetrics(rho=rho, L=L, Lq=Lq, W=W, Wq=Wq)
