"""Rotas da comparação de cenários (Fase 12): NDJSON com progresso e exportação em CSV.

POST em vez de GET porque a lista de cenários não cabe na URL. A comparação inteira é validada antes
de a resposta começar (erros viram o 422 de sempre); depois cada cenário concluído sai como uma linha
de JSON. Se o cliente fecha a conexão, o servidor para entre um cenário e outro.
"""

import json
import logging
from collections.abc import Iterator

from fastapi import APIRouter, Response
from fastapi.responses import StreamingResponse

from app.api.schemas import ErrorResponse
from app.api.schemas_scenarios import ScenarioEventOut, ScenariosRequest
from app.scenarios.compare import Plan, iter_comparison, prepare, run_comparison
from app.scenarios.csvout import comparison_csv
from app.scenarios.spec import BaseSpec, Override, ScenarioSpec

router = APIRouter(prefix="/api/scenarios", tags=["Cenários"])
log = logging.getLogger(__name__)

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}


class NdjsonResponse(StreamingResponse):
    media_type = "application/x-ndjson"


def _service(spec) -> tuple[str, dict] | None:
    return None if spec is None else (spec.distribution, spec.service_values())


def _override(item) -> Override | None:
    return None if item is None else Override(item.mode, item.value)


def build_plan(request: ScenariosRequest) -> Plan:
    """Converte o corpo da API nas estruturas do domínio e valida tudo (levanta QueueValidationError)."""
    b = request.base
    base = BaseSpec(b.model, b.lam, mu=b.mu, servers=b.servers, capacity=b.capacity, service=_service(b.service))
    scenarios = [
        ScenarioSpec(
            name=s.name, model=s.model, lam=_override(s.lam), mu=_override(s.mu),
            servers=_override(s.servers), capacity=_override(s.capacity),
            cv=_override(s.cv), k=_override(s.k), service=_service(s.service),
        )
        for s in request.scenarios
    ]
    return prepare(
        base, scenarios, simulation_time=request.simulation_time, replications=request.replications,
        warmup_time=request.warmup_time, seed=request.seed, confidence_level=request.confidence_level,
        bonferroni=request.bonferroni,
    )


def _lines(plan: Plan) -> Iterator[str]:
    try:
        for event in iter_comparison(plan):
            yield json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n"
    except Exception:   # noqa: BLE001 - depois do primeiro byte já não dá para mudar o status HTTP
        log.exception("Falha inesperada na comparação de cenários")
        yield json.dumps({
            "type": "error", "code": "internal_error",
            "message": "Falha inesperada ao comparar os cenários.",
        }) + "\n"


@router.post(
    "/compare", response_class=NdjsonResponse,
    responses={200: {"model": ScenarioEventOut, "description": "Uma linha JSON por evento (application/x-ndjson)."}, **_errors},
)
def compare_scenarios(request: ScenariosRequest) -> NdjsonResponse:
    """Compara a base com até 10 cenários, com IC pareado (números aleatórios comuns).

    Cada réplica usa fluxos independentes de chegada e serviço, as mesmas sementes em todos os cenários.
    A resposta é um NDJSON: `start`, `base`, um `scenario` por cenário concluído (com `completed` e
    `total` para o progresso) e `done` com o resultado completo. Cenário instável (ρ ≥ 1) não é
    simulado: sai com o alerta. Fechar a conexão cancela o que falta.
    """
    return NdjsonResponse(_lines(build_plan(request)))


@router.post("/export.csv", response_class=Response, responses={200: {"content": {"text/csv": {}}}, **_errors})
def export_scenarios_csv(request: ScenariosRequest) -> Response:
    """Refaz a comparação (mesmo corpo, mesma semente: resultado reproduzível) e devolve o CSV."""
    result = run_comparison(build_plan(request))
    return Response(
        comparison_csv(result), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="cenarios.csv"'},
    )
