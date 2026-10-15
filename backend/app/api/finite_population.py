"""Rotas do modelo de população finita M/M/c//N (analítico e simulação)."""

from fastapi import APIRouter

from app.analytical.finite_population import finite_population_metrics
from app.api.schemas import ErrorResponse
from app.api.schemas_realdata_extra import (
    FinitePopulationRequest, FinitePopulationResponse, FinitePopulationSimulateRequest,
    FinitePopulationSimulationResponse,
)
from app.domain.models.naming import finite_population_model_name
from app.simulation.finite_population import simulate_finite_population

router = APIRouter(prefix="/api/models/mmcn", tags=["M/M/c//N (população finita)"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


@router.post("/calculate", response_model=FinitePopulationResponse, responses=_errors)
def calculate(request: FinitePopulationRequest) -> FinitePopulationResponse:
    """Métricas analíticas do sistema fechado (N usuários, tempo de reflexão Z, c servidores)."""
    metrics = finite_population_metrics(request.mu, request.servers, request.population, request.think_time)
    return FinitePopulationResponse(
        model=finite_population_model_name(request.servers, request.population),
        population=request.population, think_time=request.think_time, servers=request.servers,
        **metrics.as_dict(),
    )


@router.post("/simulate", response_model=FinitePopulationSimulationResponse, responses=_errors)
def simulate(request: FinitePopulationSimulateRequest) -> FinitePopulationSimulationResponse:
    """Simulação de eventos discretos do sistema fechado, com réplicas e intervalos de confiança."""
    result = simulate_finite_population(
        request.population, request.think_time, request.mu, request.servers,
        request.simulation_time, request.replications, request.warmup_time,
        request.seed, request.confidence_level,
    )
    data = result.as_dict()
    data["model"] = finite_population_model_name(result.servers, result.population)
    return FinitePopulationSimulationResponse.model_validate(data)
