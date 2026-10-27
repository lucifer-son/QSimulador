"""Rotas da Fase 13: distribuições, sensibilidade Wq × λ e ajuste de amostras.

`/fit` responde em NDJSON (o p-valor por Monte Carlo pode levar alguns segundos): a amostra é validada
antes de a resposta começar (erros viram o 422 de sempre); depois cada candidata concluída sai como uma
linha de JSON. Se o cliente fecha a conexão, o servidor para entre uma candidata e outra.
"""

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.analysis.distribution import state_distribution, wait_tail_mmc
from app.analysis.fit import iter_fit
from app.analysis.sensitivity_curve import wq_vs_lambda
from app.analysis.wait_simulation import simulate_wait_survival
from app.api.schemas import ErrorResponse
from app.api.schemas_analysis import (
    AnalysisDistributionRequest, AnalysisDistributionResponse, AnalysisFitEventOut, AnalysisFitRequest,
    AnalysisSensitivityRequest, AnalysisSensitivityResponse,
)
from app.domain.service.distributions import build_distribution
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES

router = APIRouter(prefix="/api/analysis", tags=["Análise de distribuições"])
log = logging.getLogger(__name__)

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}

CLOSED_FORM_WAIT = ("mm1", "mmc")
STATE_MODELS = ("mm1", "mmc", "mm1k", "mmck")


class NdjsonResponse(StreamingResponse):
    media_type = "application/x-ndjson"


def _service(request):
    if request.service is None:
        return None, None
    return request.service.distribution, request.service.service_values()


def _no_queue(model: str) -> None:
    if model == "erlangb":
        raise QueueValidationError(
            "O Erlang-B é um sistema de perda: não há fila, então não há distribuição de espera nem P(n) por aqui.", "model")


def _require_rates(request) -> None:
    """μ é obrigatório nos modelos markovianos; o serviço geral usa `service`."""
    if request.model in ("mg1", "mgc"):
        if request.service is None:
            raise QueueValidationError("service é obrigatório nos modelos de serviço geral.", "service")
    elif request.mu is None:
        raise QueueValidationError(f"mu é obrigatório para o modelo {request.model}.", "mu")
    if request.model in ("mmc", "mmck", "mgc") and request.servers is None:
        raise QueueValidationError(f"servers é obrigatório para o modelo {request.model}.", "servers")
    if request.model in ("mm1k", "mmck") and request.capacity is None:
        raise QueueValidationError(f"capacity é obrigatório para o modelo {request.model}.", "capacity")


@router.post("/distribution", response_model=AnalysisDistributionResponse, responses=_errors)
def distribution(request: AnalysisDistributionRequest) -> dict:
    """P(n) analítica e P(Wq > t) (fórmula fechada no M/M/c; histograma da simulação nos demais).

    P(n) existe para M/M/1, M/M/c, M/M/1/K e M/M/c/K (soma 1; P(0) = 1 − ρ no M/M/1). O serviço geral não
    tem P(n) fechada. Rota síncrona de propósito: a simulação é CPU-bound e roda numa thread.
    """
    model = request.model
    _no_queue(model)
    _require_rates(request)
    out: dict = {"model": model, "states": None, "states_note": None, "wait_closed_form": None,
                 "wait_simulation": None, "wait_note": None}

    if model in STATE_MODELS:
        out["states"] = state_distribution(model, request.lam, request.mu, request.servers or 1, request.capacity).as_dict()
    else:
        out["states_note"] = ("O serviço geral não tem P(n) fechada: a aproximação de Allen–Cunneen só define as médias "
                              "(Lq, Wq...). Veja a distribuição da espera, que sai da simulação.")

    if model in CLOSED_FORM_WAIT:
        out["wait_closed_form"] = wait_tail_mmc(
            model, request.lam, request.mu, request.servers or 1, request.points, request.t_max).as_dict()
        out["wait_note"] = "Fórmula fechada: P(Wq > t) = C·exp(−(c·μ − λ)·t), com C = Erlang C."
    else:
        out["wait_note"] = ("Sem fórmula fechada neste modelo: a curva é o histograma de uma simulação FIFO, "
                            "com IC entre réplicas.")

    if model not in CLOSED_FORM_WAIT or request.simulate:
        distribution_key, values = _service(request)
        service = build_distribution(distribution_key, values) if distribution_key else None
        sim = request.simulation
        out["wait_simulation"] = simulate_wait_survival(
            model, request.lam, mu=request.mu, servers=request.servers or 1, capacity=request.capacity,
            service=service, simulation_time=sim.simulation_time, replications=sim.replications,
            warmup_time=sim.warmup_time, seed=sim.seed, confidence_level=sim.confidence_level, points=request.points,
        ).as_dict()
    return out


@router.post("/sensitivity", response_model=AnalysisSensitivityResponse, responses=_errors)
def sensitivity(request: AnalysisSensitivityRequest) -> dict:
    """Curva de Wq (e W, Lq) em função de λ, ao redor da configuração atual, com o ponto do Laboratório marcado.

    Reaproveita a varredura de λ da Fase 6. Na fila ilimitada a curva para em ρ = 0,99.
    """
    _no_queue(request.model)
    _require_rates(request)
    distribution_key, values = _service(request)
    return wq_vs_lambda(
        request.model, request.lam, mu=request.mu, servers=request.servers, capacity=request.capacity,
        distribution=distribution_key, service_values=values, span=request.span, points=request.points,
    ).as_dict()


def _lines(events: Iterator[dict]) -> Iterator[str]:
    try:
        for event in events:
            yield json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
    except Exception:   # noqa: BLE001 - depois do primeiro byte já não dá para mudar o status HTTP
        log.exception("Falha inesperada no ajuste de distribuição")
        yield json.dumps({"type": "error", "code": "internal_error",
                          "message": "Falha inesperada ao ajustar a distribuição."}) + "\n"


def _too_large() -> JSONResponse:
    mb = MAX_UPLOAD_BYTES // (1024 * 1024)
    message = f"O corpo da requisição passa do limite de {mb} MB (o mesmo do envio de CSV)."
    return JSONResponse(status_code=413, content={
        "code": "file_too_large", "message": message, "fields": [{"field": "sample", "message": message}]})


@router.post(
    "/fit", response_class=NdjsonResponse,
    responses={200: {"model": AnalysisFitEventOut, "description": "Uma linha JSON por evento (application/x-ndjson)."},
               413: {"model": ErrorResponse, "description": "Corpo maior que o limite do envio de CSV"}, **_errors},
)
def fit(request: AnalysisFitRequest, http: Request):
    """Ajusta exponencial, Erlang-k, lognormal, Weibull e uniforme por máxima verossimilhança.

    Para cada candidata: parâmetros, AIC, CV e **p-valor de aderência por Monte Carlo** (bootstrap paramétrico,
    com os parâmetros reestimados em cada réplica; não é o KS simples). A resposta é um NDJSON: `start`, uma
    `candidate` por candidata e `done` com o resultado completo (histograma, curvas, sugestão de modelo).
    """
    length = http.headers.get("content-length")
    if length is not None and length.isdigit() and int(length) > MAX_UPLOAD_BYTES:
        return _too_large()
    events = iter_fit(request.sample, kind=request.kind, bootstrap=request.bootstrap,
                      alpha=request.alpha, seed=request.seed)
    first = next(events)            # valida tudo antes do primeiro byte: erros viram o 422 de sempre

    def stream() -> Iterator[dict]:
        yield first
        yield from events

    return NdjsonResponse(_lines(stream()))
