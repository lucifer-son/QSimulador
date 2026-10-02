"""Rotas do modelo M/M/1."""

from fastapi import APIRouter

from app.analytical.mm1 import mm1_metrics
from app.api.schemas import (
    ErrorResponse,
    MM1CalculateRequest,
    MM1CalculateResponse,
    MM1SimulateRequest,
    SimulationResponse,
)
from app.simulation.mm1 import simulate_mm1

router = APIRouter(prefix="/api/models/mm1", tags=["M/M/1"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


@router.post("/calculate", response_model=MM1CalculateResponse, responses=_errors)
def calculate(request: MM1CalculateRequest) -> MM1CalculateResponse:
    """Métricas analíticas (regime estacionário). Exige λ < μ."""
    metrics = mm1_metrics(request.lam, request.mu)
    return MM1CalculateResponse(**metrics.as_dict())


# Rota síncrona (def, não async def) de propósito: a simulação é CPU-bound e,
# assim, o FastAPI a executa em uma thread, sem bloquear o servidor.
@router.post("/simulate", response_model=SimulationResponse, responses=_errors)
def simulate(request: MM1SimulateRequest) -> SimulationResponse:
    """Simulação de eventos discretos com várias replicações independentes."""
    result = simulate_mm1(
        lam=request.lam,
        mu=request.mu,
        simulation_time=request.simulation_time,
        replications=request.replications,
        warmup_time=request.warmup_time,
        seed=request.seed,
        confidence_level=request.confidence_level,
    )
    data = result.as_dict()
    data["lambda"] = data.pop("lam")
    return SimulationResponse.model_validate(data)
