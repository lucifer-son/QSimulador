"""Cálculo analítico de um ponto de experimento, para qualquer um dos quatro modelos."""

from dataclasses import dataclass

from app.analytical.erlangb import erlangb_metrics
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

    O M/M/1 traz sete métricas (a vazão é λ, como na comparação); os demais markovianos, nove; o
    Erlang-B, as do sistema de perda (bloqueio, tráfego carregado...). Os modelos de serviço geral
    (mg1 e mgc) têm módulo próprio, porque dependem da distribuição. Levanta QueueValidationError
    (ou UnstableSystemError) quando o ponto não é válido.
    """
    if model in ("mg1", "mgc"):
        raise QueueValidationError(
            f"O modelo {model} usa o serviço geral: os experimentos dele pedem `service`.", "model"
        )
    if model == "mm1":
        return {**mm1_metrics(lam, mu).as_dict(), "throughput": float(lam)}
    if model == "erlangb":
        return erlangb_metrics(lam, mu, servers).as_dict()
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
