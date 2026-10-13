"""Cálculo analítico de um ponto de experimento, para qualquer um dos quatro modelos."""

from dataclasses import dataclass

from app.analytical.mm1 import mm1_metrics
from app.analytical.mmck import queue_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError

STATUS_OK = "ok"
STATUS_UNSTABLE = "unstable"   # fora do regime estacionário (λ ≥ c·μ com fila ilimitada)
STATUS_INVALID = "invalid"     # combinação fora do domínio do modelo (ex.: K < c)


def analytical_metrics(
    model: str, lam: float, mu: float, servers: int, capacity: int | None
) -> dict[str, float]:
    """Métricas analíticas pelo conjunto de métricas do modelo.

    O M/M/1 traz sete métricas (a vazão é λ, como na comparação); os demais, nove. Levanta
    QueueValidationError (ou UnstableSystemError) quando o ponto não é válido.
    """
    if model == "mm1":
        return {**mm1_metrics(lam, mu).as_dict(), "throughput": float(lam)}
    return queue_metrics(lam, mu, servers, capacity).as_dict()


@dataclass(frozen=True)
class PointEvaluation:
    status: str
    message: str | None
    metrics: dict[str, float] | None


def evaluate_point(
    model: str, lam: float, mu: float, servers: int, capacity: int | None
) -> PointEvaluation:
    """Calcula um ponto sem interromper o experimento se ele não for válido.

    Instabilidade e combinações inválidas viram `status` e `message`; os demais pontos da faixa
    continuam sendo calculados (RF-22).
    """
    try:
        return PointEvaluation(STATUS_OK, None, analytical_metrics(model, lam, mu, servers, capacity))
    except UnstableSystemError as error:
        return PointEvaluation(STATUS_UNSTABLE, str(error), None)
    except QueueValidationError as error:
        return PointEvaluation(STATUS_INVALID, str(error), None)
