"""Rotas dos experimentos da Fase 6: varredura, comparação de servidores e sensibilidade."""

from fastapi import APIRouter

from app.api.schemas import (
    ErrorResponse,
    SensitivityRequest,
    SensitivityResponse,
    ServerComparisonRequest,
    ServerComparisonResponse,
    ServicesComparisonRequest,
    ServicesComparisonResponse,
    SweepRequest,
    SweepResponse,
)
from app.domain.validation.errors import QueueValidationError
from app.experiments.mg1 import run_mg1_sensitivity, run_mg1_sweep, run_services_comparison
from app.experiments.sensitivity import run_sensitivity
from app.experiments.sweep import SimulationSettings, run_server_comparison, run_sweep

router = APIRouter(prefix="/api/experiments", tags=["Experimentos"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


def _required_service(service):
    if service is None:
        raise QueueValidationError("service é obrigatório para o modelo mg1.", "service")
    return service


# Rotas síncronas (def) de propósito: com simulate, o cálculo é CPU-bound e o FastAPI
# as executa em uma thread, sem bloquear o servidor.
@router.post("/sweep", response_model=SweepResponse, responses=_errors)
def sweep(request: SweepRequest) -> SweepResponse:
    """Varre λ, μ, c ou K em uma faixa e devolve as métricas de cada ponto.

    Pontos instáveis ou fora do domínio do modelo são sinalizados (`status`) e os demais
    continuam sendo calculados. Com `simulate`, cada ponto estável também é simulado.
    """
    simulation = None
    if request.simulate:
        simulation = SimulationSettings(
            simulation_time=request.simulation_time,
            replications=request.replications,
            warmup_time=request.warmup_time,
            seed=request.seed,
            confidence_level=request.confidence_level,
        )
    if request.model == "mg1":
        service = _required_service(request.service)
        result = run_mg1_sweep(
            service.distribution, service.service_values(), request.variable,
            request.start, request.end, request.step, lam=request.lam, simulation=simulation,
        )
        return SweepResponse.model_validate(result.as_dict())
    result = run_sweep(
        request.model, request.variable, request.start, request.end, request.step,
        lam=request.lam, mu=request.mu, servers=request.servers, capacity=request.capacity,
        simulation=simulation,
    )
    return SweepResponse.model_validate(result.as_dict())


@router.post("/servers", response_model=ServerComparisonResponse, responses=_errors)
def compare_servers(request: ServerComparisonRequest) -> ServerComparisonResponse:
    """Compara o desempenho com números diferentes de servidores, variando λ na mesma faixa."""
    result = run_server_comparison(
        request.servers_list, request.mu, request.start, request.end, request.step,
        capacity=request.capacity,
    )
    return ServerComparisonResponse.model_validate(result.as_dict())


@router.post("/sensitivity", response_model=SensitivityResponse, responses=_errors)
def sensitivity(request: SensitivityRequest) -> SensitivityResponse:
    """Mede quanto cada métrica muda ao perturbar cada parâmetro em torno do ponto base."""
    if request.model == "mg1":
        service = _required_service(request.service)
        result = run_mg1_sensitivity(
            service.distribution, service.service_values(), request.lam, request.delta_pct
        )
        return SensitivityResponse.model_validate(result.as_dict())
    if request.mu is None:
        raise QueueValidationError("mu é obrigatório para o modelo " + request.model + ".", "mu")
    result = run_sensitivity(
        request.model, request.lam, request.mu,
        servers=request.servers, capacity=request.capacity, delta_pct=request.delta_pct,
    )
    return SensitivityResponse.model_validate(result.as_dict())


@router.post("/services", response_model=ServicesComparisonResponse, responses=_errors)
def compare_services(request: ServicesComparisonRequest) -> ServicesComparisonResponse:
    """Compara distribuições de serviço no M/G/1, variando λ na mesma faixa para todas."""
    result = run_services_comparison(
        [(spec.distribution, spec.service_values()) for spec in request.services],
        request.start, request.end, request.step,
    )
    return ServicesComparisonResponse.model_validate(result.as_dict())
