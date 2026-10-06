"""Rotas dos modelos M/M/c, M/M/1/K e M/M/c/K.

Cada modelo tem três rotas (`calculate`, `simulate` e `compare`), geradas por
uma mesma fábrica: o que muda entre os modelos é só o formato da entrada e
como ela vira o par (servers, capacity).
"""

from collections.abc import Callable

from fastapi import APIRouter

from app.analysis.comparison import compare_queue
from app.analytical.mmck import queue_metrics
from app.api.schemas import (
    ErrorResponse,
    MMCCalculateRequest,
    MMCKCalculateRequest,
    MMCKSimulateRequest,
    MMCSimulateRequest,
    MM1KCalculateRequest,
    MM1KSimulateRequest,
    QueueCalculateResponse,
    QueueComparisonResponse,
    QueueSimulationResponse,
)
from app.domain.models.naming import queue_model_name
from app.simulation.mmck import simulate_mmck

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}

Shape = Callable[[object], tuple[int, int | None]]


def _with_model_fields(data: dict, servers: int, capacity: int | None) -> dict:
    data["lambda"] = data.pop("lam")
    data["model"] = queue_model_name(servers, capacity)
    return data


def build_router(
    prefix: str,
    tag: str,
    calculate_request: type,
    simulate_request: type,
    shape: Shape,
) -> APIRouter:
    """Cria as rotas calculate, simulate e compare de um modelo.

    `shape(request)` devolve (servers, capacity) a partir da requisição.
    """
    router = APIRouter(prefix=prefix, tags=[tag])

    @router.post("/calculate", response_model=QueueCalculateResponse, responses=_errors)
    def calculate(request: calculate_request) -> QueueCalculateResponse:
        """Métricas analíticas (regime estacionário)."""
        servers, capacity = shape(request)
        metrics = queue_metrics(request.lam, request.mu, servers, capacity)
        return QueueCalculateResponse(
            model=queue_model_name(servers, capacity),
            servers=servers,
            capacity=capacity,
            **metrics.as_dict(),
        )

    # Rotas síncronas (def) de propósito: a simulação é CPU-bound e, assim,
    # o FastAPI as executa em uma thread, sem bloquear o servidor.
    @router.post("/simulate", response_model=QueueSimulationResponse, responses=_errors)
    def simulate(request: simulate_request) -> QueueSimulationResponse:
        """Simulação de eventos discretos com várias replicações independentes."""
        servers, capacity = shape(request)
        result = simulate_mmck(
            request.lam, request.mu, servers, capacity,
            simulation_time=request.simulation_time,
            replications=request.replications,
            warmup_time=request.warmup_time,
            seed=request.seed,
            confidence_level=request.confidence_level,
        )
        return QueueSimulationResponse.model_validate(
            _with_model_fields(result.as_dict(), servers, capacity)
        )

    @router.post("/compare", response_model=QueueComparisonResponse, responses=_errors)
    def compare(request: simulate_request) -> QueueComparisonResponse:
        """Compara o analítico com a simulação, métrica a métrica."""
        servers, capacity = shape(request)
        result = compare_queue(
            request.lam, request.mu, servers, capacity,
            simulation_time=request.simulation_time,
            replications=request.replications,
            warmup_time=request.warmup_time,
            seed=request.seed,
            confidence_level=request.confidence_level,
        )
        return QueueComparisonResponse.model_validate(
            _with_model_fields(result.as_dict(), servers, capacity)
        )

    return router


mmc_router = build_router(
    "/api/models/mmc", "M/M/c", MMCCalculateRequest, MMCSimulateRequest,
    shape=lambda r: (r.servers, None),
)
mm1k_router = build_router(
    "/api/models/mm1k", "M/M/1/K", MM1KCalculateRequest, MM1KSimulateRequest,
    shape=lambda r: (1, r.capacity),
)
mmck_router = build_router(
    "/api/models/mmck", "M/M/c/K", MMCKCalculateRequest, MMCKSimulateRequest,
    shape=lambda r: (r.servers, r.capacity),
)
