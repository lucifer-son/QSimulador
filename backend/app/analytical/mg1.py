"""Modelo analítico M/G/1 (Pollaczek-Khinchine) e M/D/1 (caso CV = 0).

Chegadas de Poisson (λ), um servidor, fila ilimitada, FIFO. O serviço pode ter qualquer
distribuição; só a média e a variância entram nas fórmulas:

    ρ = λ·E[S];  Lq = (ρ² + λ²·Var(S)) / (2(1 − ρ));  Wq = Lq/λ;  W = Wq + E[S];  L = λW.
"""

from app.domain.metrics.queue_metrics import QueueMetrics
from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.mg1 import validate_mg1_parameters


def mg1_metrics(lam: float, service: ServiceDistribution) -> QueueMetrics:
    """ρ, L, Lq, W, Wq e P0 de um M/G/1. Levanta UnstableSystemError se ρ ≥ 1."""
    lam = validate_mg1_parameters(lam, service)
    rho = lam * service.mean
    Lq = (rho**2 + lam**2 * service.variance) / (2 * (1 - rho))
    Wq = Lq / lam
    W = Wq + service.mean
    return QueueMetrics(rho=rho, L=lam * W, Lq=Lq, W=W, Wq=Wq, p0=1 - rho)
