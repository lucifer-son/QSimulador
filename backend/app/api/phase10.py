"""Rotas da Fase 10: Erlang-B (M/M/c/c, com dimensionamento) e M/G/c (Allen–Cunneen)."""

from fastapi import APIRouter

from app.analysis.comparison_phase10 import compare_erlangb, compare_mgc
from app.analytical.erlangb import erlangb_metrics, erlangb_size
from app.analytical.mgc import is_exact, mgc_metrics, validity_warnings
from app.api.schemas import ErrorResponse, QueueComparisonResponse, QueueSimulationResponse
from app.api.schemas_phase10 import (
    ErlangBCalculateRequest,
    ErlangBCalculateResponse,
    ErlangBSimulateRequest,
    ErlangBSizeRequest,
    ErlangBSizeResponse,
    MGCCalculateRequest,
    MGCCalculateResponse,
    MGCComparisonResponse,
    MGCSimulateRequest,
    MGCSimulationResponse,
)
from app.domain.models.naming import erlang_b_model_name, multi_server_service_model_name
from app.domain.service.distributions import build_distribution
from app.simulation.mgc import simulate_mgc
from app.simulation.mmck import simulate_mmck

erlangb_router = APIRouter(prefix="/api/models/erlangb", tags=["Erlang-B (M/M/c/c)"])
mgc_router = APIRouter(prefix="/api/models/mgc", tags=["M/G/c"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


# ---------- Erlang-B ----------

def _queue_fields(data: dict, servers: int) -> dict:
    data["lambda"] = data.pop("lam")
    data["model"] = erlang_b_model_name(servers)
    data["capacity"] = servers
    return data


@erlangb_router.post("/calculate", response_model=ErlangBCalculateResponse, responses=_errors)
def erlangb_calculate(request: ErlangBCalculateRequest) -> ErlangBCalculateResponse:
    """Métricas do sistema de perda: bloqueio de Erlang B, tráfego carregado e utilização."""
    metrics = erlangb_metrics(request.lam, request.mu, request.servers)
    return ErlangBCalculateResponse(
        model=erlang_b_model_name(request.servers), servers=request.servers,
        capacity=request.servers, **metrics.as_dict(),
    )


# Rotas síncronas (def) de propósito: a simulação é CPU-bound e o FastAPI as executa em thread.
@erlangb_router.post("/simulate", response_model=QueueSimulationResponse, responses=_errors)
def erlangb_simulate(request: ErlangBSimulateRequest) -> QueueSimulationResponse:
    """Simulação do sistema de perda: o motor do M/M/c/K com capacidade K = c."""
    result = simulate_mmck(
        request.lam, request.mu, request.servers, request.servers,
        simulation_time=request.simulation_time, replications=request.replications,
        warmup_time=request.warmup_time, seed=request.seed, confidence_level=request.confidence_level,
    )
    return QueueSimulationResponse.model_validate(_queue_fields(result.as_dict(), request.servers))


@erlangb_router.post("/compare", response_model=QueueComparisonResponse, responses=_errors)
def erlangb_compare(request: ErlangBSimulateRequest) -> QueueComparisonResponse:
    """Compara o Erlang-B analítico com a simulação, métrica a métrica (erro e IC)."""
    result = compare_erlangb(
        request.lam, request.mu, request.servers,
        simulation_time=request.simulation_time, replications=request.replications,
        warmup_time=request.warmup_time, seed=request.seed, confidence_level=request.confidence_level,
    )
    return QueueComparisonResponse.model_validate(_queue_fields(result.as_dict(), request.servers))


@erlangb_router.post("/size", response_model=ErlangBSizeResponse, responses=_errors)
def erlangb_size_route(request: ErlangBSizeRequest) -> ErlangBSizeResponse:
    """Menor número de servidores (linhas, canais) que mantém o bloqueio abaixo do alvo."""
    return ErlangBSizeResponse.model_validate(
        erlangb_size(request.lam, request.mu, request.target_blocking).as_dict()
    )


# ---------- M/G/c ----------

def _with_fields(data: dict, distribution: str, servers: int) -> dict:
    data["lambda"] = data.pop("lam")
    data["model"] = multi_server_service_model_name(distribution, servers)
    return data


def _approximation_info(service, servers: int, lam: float) -> dict:
    rho = lam * service.mean / servers
    return {"exact": is_exact(service, servers), "warnings": validity_warnings(rho, service.cv, servers)}


@mgc_router.post("/calculate", response_model=MGCCalculateResponse, responses=_errors)
def mgc_calculate(request: MGCCalculateRequest) -> MGCCalculateResponse:
    """Aproximação de Allen–Cunneen. Exige ρ = λ·E[S]/c < 1."""
    service = build_distribution(request.distribution, request.service_values())
    metrics = mgc_metrics(request.lam, service, request.servers)
    return MGCCalculateResponse(
        model=multi_server_service_model_name(service.key, request.servers), servers=request.servers,
        service=service.describe(), **_approximation_info(service, request.servers, request.lam),
        **metrics.as_dict(),
    )


@mgc_router.post("/simulate", response_model=MGCSimulationResponse, responses=_errors)
def mgc_simulate(request: MGCSimulateRequest) -> MGCSimulationResponse:
    """Simulação de eventos discretos com o serviço amostrado da distribuição escolhida."""
    service = build_distribution(request.distribution, request.service_values())
    result = simulate_mgc(
        request.lam, service, request.servers, request.simulation_time, request.replications,
        request.warmup_time, request.seed, request.confidence_level,
    )
    return MGCSimulationResponse.model_validate(_with_fields(result.as_dict(), service.key, request.servers))


@mgc_router.post("/compare", response_model=MGCComparisonResponse, responses=_errors)
def mgc_compare(request: MGCSimulateRequest) -> MGCComparisonResponse:
    """Compara a aproximação com a simulação: o erro mostra a precisão da aproximação."""
    service = build_distribution(request.distribution, request.service_values())
    result = compare_mgc(
        request.lam, service, request.servers, request.simulation_time, request.replications,
        request.warmup_time, request.seed, request.confidence_level,
    )
    data = _with_fields(result.as_dict(), service.key, request.servers)
    data.update(_approximation_info(service, request.servers, request.lam))
    return MGCComparisonResponse.model_validate(data)
