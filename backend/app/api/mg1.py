"""Rotas do serviço geral: M/G/1 e M/D/1 (e o catálogo de distribuições).

O M/D/1 é o M/G/1 com distribuição determinística; só o nome muda na resposta.
"""

from fastapi import APIRouter

from app.analysis.comparison_mg1 import compare_mg1
from app.analytical.mg1 import mg1_metrics
from app.api.schemas import ErrorResponse
from app.api.schemas_mg1 import (
    DistributionCatalogResponse,
    MG1CalculateRequest,
    MG1CalculateResponse,
    MG1ComparisonResponse,
    MG1SimulateRequest,
    MG1SimulationResponse,
)
from app.domain.models.naming import service_model_name
from app.domain.service.distributions import CATALOG, build_distribution
from app.simulation.mg1 import simulate_mg1

router = APIRouter(prefix="/api/models/mg1", tags=["M/G/1 e M/D/1"])
distributions_router = APIRouter(prefix="/api/distributions", tags=["Distribuições de serviço"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


def _with_model_fields(data: dict, distribution: str) -> dict:
    data["lambda"] = data.pop("lam")
    data["model"] = service_model_name(distribution)
    return data


@router.post("/calculate", response_model=MG1CalculateResponse, responses=_errors)
def calculate(request: MG1CalculateRequest) -> MG1CalculateResponse:
    """Métricas analíticas (Pollaczek-Khinchine). Exige ρ = λ·E[S] < 1."""
    service = build_distribution(request.distribution, request.service_values())
    metrics = mg1_metrics(request.lam, service)
    return MG1CalculateResponse(
        model=service_model_name(service.key), service=service.describe(), **metrics.as_dict()
    )


# Rotas síncronas (def) de propósito: a simulação é CPU-bound e o FastAPI as executa em thread.
@router.post("/simulate", response_model=MG1SimulationResponse, responses=_errors)
def simulate(request: MG1SimulateRequest) -> MG1SimulationResponse:
    """Simulação de eventos discretos com o serviço amostrado da distribuição escolhida."""
    service = build_distribution(request.distribution, request.service_values())
    result = simulate_mg1(
        request.lam, service, request.simulation_time, request.replications,
        request.warmup_time, request.seed, request.confidence_level,
    )
    return MG1SimulationResponse.model_validate(_with_model_fields(result.as_dict(), service.key))


@router.post("/compare", response_model=MG1ComparisonResponse, responses=_errors)
def compare(request: MG1SimulateRequest) -> MG1ComparisonResponse:
    """Compara o analítico com a simulação, métrica a métrica (erro e IC)."""
    service = build_distribution(request.distribution, request.service_values())
    result = compare_mg1(
        request.lam, service, request.simulation_time, request.replications,
        request.warmup_time, request.seed, request.confidence_level,
    )
    return MG1ComparisonResponse.model_validate(_with_model_fields(result.as_dict(), service.key))


@distributions_router.get("", response_model=DistributionCatalogResponse)
def list_distributions() -> DistributionCatalogResponse:
    """Distribuições de serviço disponíveis, com os parâmetros de cada uma."""
    return DistributionCatalogResponse.model_validate(
        {"distributions": [
            {"key": s.key, "label": s.label, "description": s.description, "accepts_mean": s.accepts_mean,
             "parameters": [vars(p) for p in s.parameters], "example": s.example}
            for s in CATALOG
        ]}
    )
