"""Rotas do modelo fechado M/M/c//N (população finita)."""

from fastapi import APIRouter

from app.analytical.closed import closed_metrics
from app.api.realdata_schemas import (
    ClosedCalculateRequest,
    ClosedCalculateResponse,
    ClosedSimulateRequest,
    ClosedSimulationResponse,
)
from app.api.schemas import ErrorResponse
from app.simulation.closed import simulate_closed

router = APIRouter(prefix="/api/models/mmcn", tags=["M/M/c//N (fechado)"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


def _name(servers: int, users: int) -> str:
    return f"M/M/{servers}//{users}"


@router.post("/calculate", response_model=ClosedCalculateResponse, responses=_errors)
def calculate(request: ClosedCalculateRequest) -> ClosedCalculateResponse:
    """Métricas analíticas do sistema fechado (N usuários, tempo de reflexão Z, c servidores)."""
    metrics = closed_metrics(request.users, request.think_time, request.mu, request.servers)
    return ClosedCalculateResponse(
        model=_name(request.servers, request.users), users=request.users,
        think_time=request.think_time, servers=request.servers, **metrics.as_dict(),
    )


@router.post("/simulate", response_model=ClosedSimulationResponse, responses=_errors)
def simulate(request: ClosedSimulateRequest) -> ClosedSimulationResponse:
    """Simulação de eventos discretos do sistema fechado, com réplicas e intervalos de confiança."""
    result = simulate_closed(
        request.users, request.think_time, request.mu, request.servers,
        request.simulation_time, request.replications, request.warmup_time,
        request.seed, request.confidence_level,
    )
    data = result.as_dict()
    data["model"] = _name(result.servers, result.users)
    return ClosedSimulationResponse.model_validate(data)
