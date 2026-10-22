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
from app.domain.validation.experiments import GENERAL_SERVICE_MODELS
from app.experiments.general import (
    run_general_sensitivity,
    run_general_server_comparison,
    run_general_sweep,
    run_services_comparison,
)
from app.experiments.sensitivity import run_sensitivity
from app.experiments.sweep import SimulationSettings, run_server_comparison, run_sweep

router = APIRouter(prefix="/api/experiments", tags=["Experimentos"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


def _required_service(service, model: str = "mg1"):
    if service is None:
        raise QueueValidationError(f"service é obrigatório para o modelo {model}.", "service")
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
    if request.model in GENERAL_SERVICE_MODELS:
        service = _required_service(request.service, request.model)
        result = run_general_sweep(
            request.model, service.distribution, service.service_values(), request.variable,
            request.start, request.end, request.step, lam=request.lam, servers=request.servers,
            simulation=simulation,
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
    """Compara o desempenho com números diferentes de servidores, variando λ na mesma faixa.

    Cobre M/M/c, M/M/c/K, Erlang-B (curva clássica do bloqueio) e M/G/c (com o serviço dado).
    """
    if request.model == "mgc":
        service = _required_service(request.service, "mgc")
        result = run_general_server_comparison(
            service.distribution, service.service_values(), request.servers_list,
            request.start, request.end, request.step,
        )
        return ServerComparisonResponse.model_validate(result.as_dict())
    result = run_server_comparison(
        request.servers_list, request.mu, request.start, request.end, request.step,
        capacity=request.capacity, model=request.model,
    )
    return ServerComparisonResponse.model_validate(result.as_dict())


@router.post("/sensitivity", response_model=SensitivityResponse, responses=_errors)
def sensitivity(request: SensitivityRequest) -> SensitivityResponse:
    """Mede quanto cada métrica muda ao perturbar cada parâmetro em torno do ponto base."""
    if request.model in GENERAL_SERVICE_MODELS:
        service = _required_service(request.service, request.model)
        result = run_general_sensitivity(
            request.model, service.distribution, service.service_values(), request.lam,
            request.delta_pct, servers=request.servers,
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
    """Compara distribuições de serviço no M/G/1 ou no M/G/c (c fixo), variando λ na mesma faixa."""
    result = run_services_comparison(
        [(spec.distribution, spec.service_values()) for spec in request.services],
        request.start, request.end, request.step,
        model=request.model, servers=request.servers,
    )
    return ServicesComparisonResponse.model_validate(result.as_dict())
