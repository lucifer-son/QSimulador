"""Rotas do cruzamento semaforizado (/api/traffic, Fase 13.1).

- simulate: um plano, com réplicas e IC (JSON).
- compare e sweep: NDJSON com progresso (como /api/scenarios/compare); fechar a conexão cancela o resto.
- video/estimate e video/validate: multipart com as planilhas do protocolo (Fase 13.2: 2 a 4 aproximações,
  classes de veículos com `class_factors`, testes de hipótese e exportação CSV da validação).
- video/sessions/compare: duas sessões (manhã × tarde) lado a lado, a partir de duas respostas de video/estimate.
- *.csv: refazem o cálculo com o mesmo corpo e a mesma semente (resultado reproduzível).
"""

import json
import logging
from collections.abc import Iterator
from typing import Annotated

from fastapi import APIRouter, File, Form, Response, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse

from app.api.schemas import ErrorResponse
from app.api.schemas_traffic import (
    CompareRequest, SessionsCompareRequest, SessionsCompareOut, SimulateRequest, SweepRequest, TrafficEventOut, TrafficResultOut,
    VideoEstimateOut, VideoValidationOut,
)
from app.domain.validation.errors import InvalidDatasetError, QueueValidationError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES
from app.traffic.compare import (
    ComparePlan, PlanSpec, SweepPlan, _finite, iter_compare, iter_sweep, prepare_compare, prepare_sweep,
    run_compare, run_sweep,
)
from app.traffic.csvout import compare_csv, sessions_csv, simulate_csv, sweep_csv, validation_csv
from app.traffic.report import simulate_report
from app.traffic.run import prepare_settings, run_plan
from app.traffic.service import intersection_from_values
from app.traffic.sessions import compare_estimates
from app.traffic.validate import boost_replications, validate_session
from app.traffic.video import (
    DEFAULT_CORE, DEFAULT_MAX_HEADWAY, DEFAULT_MIN_RUN, DEFAULT_PROFILE_BLOCK, estimate, load_session,
)

router = APIRouter(prefix="/api/traffic", tags=["Cruzamento semaforizado"])
log = logging.getLogger(__name__)

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros ou arquivos inválidos"}}
_upload_errors = {**_errors, 413: {"model": ErrorResponse, "description": "Arquivo acima do limite"}}


class NdjsonResponse(StreamingResponse):
    media_type = "application/x-ndjson"


def _intersection(request):
    return intersection_from_values([p.model_dump() for p in request.phases], request.offset, [a.spec() for a in request.approaches])


def _run_kwargs(request) -> dict:
    return dict(simulation_time=request.simulation_time, replications=request.replications,
                warmup_time=request.warmup_time, seed=request.seed, confidence_level=request.confidence_level)


def _simulate(request: SimulateRequest):
    inter = _intersection(request)
    settings = prepare_settings(inter, series_step=request.series_step, **_run_kwargs(request))
    return inter, settings


def _compare_plan(request: CompareRequest) -> ComparePlan:
    specs = []
    for i, plan in enumerate(request.scenarios):
        specs.append(PlanSpec(plan.name, tuple(None if x is None else x.values() for x in plan.phases)))
    return prepare_compare(_intersection(request), specs, bonferroni=request.bonferroni,
                           series_step=request.series_step, **_run_kwargs(request))


def _sweep_plan(request: SweepRequest) -> SweepPlan:
    return prepare_sweep(_intersection(request), min_green=list(request.min_green), step=request.step,
                         pair=None if request.pair is None else list(request.pair), **_run_kwargs(request))


def _lines(events: Iterator[dict], what: str) -> Iterator[str]:
    try:
        for event in events:
            yield json.dumps(_finite(event), ensure_ascii=False, allow_nan=False) + "\n"
    except Exception:   # noqa: BLE001 - depois do primeiro byte já não dá para mudar o status HTTP
        log.exception("Falha inesperada em %s", what)
        yield json.dumps({"type": "error", "code": "internal_error", "message": f"Falha inesperada em {what}."}) + "\n"


_CSV = {"content": {"text/csv": {}}}


def _csv(text: str, name: str) -> Response:
    return Response(text, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="{name}"'})


@router.post("/simulate", response_model=TrafficResultOut, responses=_errors)
def simulate(request: SimulateRequest) -> dict:
    """Simula o cruzamento (duas aproximações, ciclo fixo compartilhado) e devolve filas, atrasos e vazão com IC.

    Cada réplica usa fluxos independentes de chegada e de intervalo de descarga por aproximação. O atraso é
    dado de duas formas: dos veículos que já cruzaram e **com os pendentes** (quem ainda espera em T, contado só até T,
    limite inferior). `reference` traz a aproximação analítica (Webster para x < 1; fluida para x ≥ 1), sempre com `exact = false`.
    """
    inter, settings = _simulate(request)
    return simulate_report(inter, settings, run_plan(inter, settings))


@router.post("/export.csv", response_class=Response, responses={200: _CSV, **_errors})
def export_simulation_csv(request: SimulateRequest) -> Response:
    inter, settings = _simulate(request)
    return _csv(simulate_csv(simulate_report(inter, settings, run_plan(inter, settings))), "cruzamento.csv")


@router.post("/compare", response_class=NdjsonResponse,
             responses={200: {"model": TrafficEventOut, "description": "Uma linha JSON por evento (application/x-ndjson)."}, **_errors})
def compare_plans(request: CompareRequest) -> NdjsonResponse:
    """Compara até 10 planos alternativos com a referência, com IC pareado (números aleatórios comuns).

    Eventos: `start`, `base`, um `plan` por plano (com `completed` e `total`) e `done` com o resultado completo.
    Se o ciclo mudar em relação à referência, o plano traz o aviso `cycle_changed`.
    """
    return NdjsonResponse(_lines(iter_compare(_compare_plan(request)), "a comparação de planos"))


@router.post("/compare/export.csv", response_class=Response, responses={200: _CSV, **_errors})
def export_compare_csv(request: CompareRequest) -> Response:
    return _csv(compare_csv(run_compare(_compare_plan(request))), "cruzamento-planos.csv")


@router.post("/sweep", response_class=NdjsonResponse,
             responses={200: {"model": TrafficEventOut, "description": "Uma linha JSON por evento (application/x-ndjson)."}, **_errors})
def sweep_green_split(request: SweepRequest) -> NdjsonResponse:
    """Varre a divisão do verde mantendo o ciclo (g1 + g2 constante) e devolve a curva de atraso do cruzamento.

    Eventos: `start`, um `point` por divisão e `done` com `best_index` e, para cada ponto, `vs_best`
    (`best`, `worse`, `indistinguishable`): a comparação pareada com o melhor. O ciclo ótimo de Webster
    vem como referência aproximada.
    """
    return NdjsonResponse(_lines(iter_sweep(_sweep_plan(request)), "a varredura do verde"))


@router.post("/sweep/export.csv", response_class=Response, responses={200: _CSV, **_errors})
def export_sweep_csv(request: SweepRequest) -> Response:
    return _csv(sweep_csv(run_sweep(_sweep_plan(request))), "cruzamento-varredura.csv")


# ---------- dados do vídeo ----------

def _read_csv(file: UploadFile | None, label: str, *, required: bool) -> bytes | None | JSONResponse:
    if file is None or not (file.filename or ""):
        if required:
            raise InvalidDatasetError(f"Envie o arquivo CSV de {label}.", label)
        return None
    if not file.filename.lower().endswith(".csv"):
        raise InvalidDatasetError(f"{label}: envie um arquivo com extensão .csv.", label)
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        message = f"O arquivo {label} passa do limite de {mb} MB."
        return JSONResponse(status_code=413, content={"code": "file_too_large", "message": message,
                                                      "fields": [{"field": label, "message": message}]})
    return content


def _class_factors(text: str | None) -> dict | None:
    if text is None or not text.strip():
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        raise QueueValidationError("class_factors deve ser um JSON válido, por exemplo {\"carro\": 1, \"moto\": 0.33}.", "class_factors") from None
    if not isinstance(value, dict):
        raise QueueValidationError("class_factors deve ser um objeto nome da classe → fator.", "class_factors")
    return value


def _session(signal_events, counts, crossings, trajectories, session_id, approach_ids, class_factors=None):
    contents = []
    for file, label, required in ((signal_events, "signal_events", True), (counts, "counts", True),
                                  (crossings, "crossings", False), (trajectories, "trajectories", False)):
        content = _read_csv(file, label, required=required)
        if isinstance(content, JSONResponse):
            return content
        contents.append(content)
    ids = None
    if approach_ids:
        parts = [x.strip() for x in approach_ids.split(",") if x.strip()]
        if not 2 <= len(parts) <= 4 or len(set(parts)) != len(parts):
            raise QueueValidationError(
                "approach_ids deve ter de dois a quatro identificadores diferentes, separados por vírgula.", "approach_ids")
        ids = tuple(parts)
    return load_session(*contents, session_id=session_id or None, approach_ids=ids, class_factors=_class_factors(class_factors))


_FILES = (
    "signal_events: eventos semafóricos (timestamp, approach_id, signal_state). counts: contagens por intervalo "
    "(interval_start, interval_end, approach_id, arrivals, departures, queue_count, queue_visible). crossings (opcional): "
    "um cruzamento da linha de retenção por linha (crossing_time, approach_id). trajectories (opcional): veículos acompanhados."
)


@router.post("/video/estimate", response_model=VideoEstimateOut, responses=_upload_errors, description=(
    "Lê as planilhas do protocolo e estima plano, offset, chegadas por bloco, ℓ, h e amarelo utilizável. "
    "Nada é preenchido por suposição: dado ausente em uma célula obrigatória recusa o arquivo (com a linha), "
    "e o que não puder ser estimado volta como `null` e vira o aviso `not_informed` no cruzamento. " + _FILES))
def video_estimate(
    signal_events: Annotated[UploadFile, File(description="CSV dos eventos semafóricos.")],
    counts: Annotated[UploadFile, File(description="CSV das contagens por intervalo.")],
    crossings: Annotated[UploadFile | None, File(description="CSV dos cruzamentos da linha de retenção (necessário para ℓ, h e o amarelo utilizável).")] = None,
    trajectories: Annotated[UploadFile | None, File(description="CSV dos veículos acompanhados (para o atraso observado).")] = None,
    session_id: Annotated[str | None, Form(description="Sessão a usar, se os arquivos tiverem mais de uma.")] = None,
    approach_ids: Annotated[str | None, Form(description="De 2 a 4 aproximações, separadas por vírgula, na ordem das fases (a 1ª é a da fase 1).")] = None,
    class_factors: Annotated[str | None, Form(description="JSON nome da classe → fator de equivalência em carros. Obrigatório se as contagens tiverem `vehicle_class`; sem valor padrão.")] = None,
    max_headway: Annotated[float, Form(description="Intervalo máximo (s) entre veículos para contar como descarga saturada.")] = DEFAULT_MAX_HEADWAY,
    min_run: Annotated[int, Form(description="Veículos mínimos da sequência saturada de um verde.")] = DEFAULT_MIN_RUN,
    core: Annotated[int, Form(description="Veículos da cabeça da fila usados no ajuste da reta de descarga.")] = DEFAULT_CORE,
    profile_block: Annotated[float, Form(description="Duração (s) dos blocos do perfil de chegadas sugerido.")] = DEFAULT_PROFILE_BLOCK,
    confidence_level: Annotated[float, Form()] = 0.95,
):
    session = _session(signal_events, counts, crossings, trajectories, session_id, approach_ids, class_factors)
    if isinstance(session, JSONResponse):
        return session
    return _finite(estimate(session, max_headway=max_headway, min_run=min_run, core=core,
                            profile_block=profile_block, level=confidence_level))


def _validation(
    signal_events, counts, config, crossings, trajectories, session_id, approach_ids, class_factors, replications, seed,
    confidence_level, tolerance_delay, tolerance_departures,
):
    """Monta a sessão e o cruzamento (as chegadas são as contagens observadas, com o tamanho real do trabalho) e valida."""
    session = _session(signal_events, counts, crossings, trajectories, session_id, approach_ids, class_factors)
    if isinstance(session, JSONResponse):
        return session
    try:
        body = json.loads(config)
    except json.JSONDecodeError:
        raise QueueValidationError("config deve ser um JSON válido.", "config") from None
    if not isinstance(body, dict):
        raise QueueValidationError("config deve ser um objeto JSON.", "config")
    items = body.get("approaches") or []
    approaches = []
    for i, item in enumerate(items):
        item = item if isinstance(item, dict) else {}
        h = item.get("headway")
        spec = None
        if isinstance(h, dict) and "distribution" in h:
            spec = (h["distribution"], {k: v for k, v in h.items() if k != "distribution"})
        profile = None
        if i < len(session.approach_ids):
            with_classes = bool(item.get("classes")) and bool(session.classes)
            if item.get("classes") and not session.classes:
                raise QueueValidationError(
                    "O cruzamento tem classes de veículos, mas as contagens do vídeo não têm a coluna vehicle_class.",
                    f"config.approaches.{i}.classes")
            profile = [{"duration": d["end"] - d["start"], "count": d["arrivals"],
                        **({"class_counts": dict(d["by_class"])} if with_classes else {})}
                       for d in session.counts[session.approach_ids[i]]]
        approaches.append({**item, "headway": spec, "lam": None, "profile": profile})
    inter = intersection_from_values(body.get("phases"), body.get("offset"), approaches)
    settings = prepare_settings(inter, simulation_time=session.horizon, replications=replications, warmup_time=0.0,
                                seed=seed, confidence_level=confidence_level)
    settings = boost_replications(settings, inter)
    result = validate_session(session, inter, settings, tolerance_delay=tolerance_delay, tolerance_departures=tolerance_departures)
    result["settings"]["requested_replications"] = replications
    return _finite(result)


_VALIDATE_DESC = (
    "Simula o plano observado com as chegadas do vídeo e compara com a fila e as saídas observadas, intervalo a intervalo. "
    "As chegadas usam as contagens observadas (número fixo por intervalo, por classe quando houver). A resposta traz erros "
    "(viés, MAE, RMSE), a cobertura da faixa simulada e, em `tests`, testes de hipótese (aderência por Monte Carlo, KS e "
    "Mann-Whitney do atraso e, se você informar `tolerance_delay` e `tolerance_departures`, a equivalência TOST), com "
    "p-valor ajustado por Holm. Não há tolerância padrão nem limite de aprovação. "
)


@router.post("/video/validate", response_model=VideoValidationOut, responses=_upload_errors, description=_VALIDATE_DESC + _FILES)
def video_validate(
    signal_events: Annotated[UploadFile, File()],
    counts: Annotated[UploadFile, File()],
    config: Annotated[str, Form(description="JSON do cruzamento (phases, offset, approaches com headway etc.) — o corpo de /simulate sem as chegadas, que vêm das contagens.")],
    crossings: Annotated[UploadFile | None, File()] = None,
    trajectories: Annotated[UploadFile | None, File()] = None,
    session_id: Annotated[str | None, Form()] = None,
    approach_ids: Annotated[str | None, Form()] = None,
    class_factors: Annotated[str | None, Form()] = None,
    replications: Annotated[int, Form()] = 30,
    seed: Annotated[int | None, Form()] = None,
    confidence_level: Annotated[float, Form()] = 0.95,
    tolerance_delay: Annotated[float | None, Form(description="Margem (s) do teste de equivalência do atraso médio. Sem valor padrão.")] = None,
    tolerance_departures: Annotated[float | None, Form(description="Margem (fração do total observado, ex.: 0,05) do teste de equivalência das saídas. Sem valor padrão.")] = None,
):
    return _validation(signal_events, counts, config, crossings, trajectories, session_id, approach_ids, class_factors,
                       replications, seed, confidence_level, tolerance_delay, tolerance_departures)


@router.post("/video/validate/export.csv", response_class=Response, responses={200: _CSV, **_upload_errors}, description=(
    "Os mesmos parâmetros de /video/validate; devolve o CSV com o resumo dos erros, o intervalo a intervalo e os testes. "
    "Refaz o cálculo com a mesma semente: informe `seed` para o CSV bater com a tela."))
def video_validate_csv(
    signal_events: Annotated[UploadFile, File()],
    counts: Annotated[UploadFile, File()],
    config: Annotated[str, Form()],
    crossings: Annotated[UploadFile | None, File()] = None,
    trajectories: Annotated[UploadFile | None, File()] = None,
    session_id: Annotated[str | None, Form()] = None,
    approach_ids: Annotated[str | None, Form()] = None,
    class_factors: Annotated[str | None, Form()] = None,
    replications: Annotated[int, Form()] = 30,
    seed: Annotated[int | None, Form()] = None,
    confidence_level: Annotated[float, Form()] = 0.95,
    tolerance_delay: Annotated[float | None, Form()] = None,
    tolerance_departures: Annotated[float | None, Form()] = None,
):
    result = _validation(signal_events, counts, config, crossings, trajectories, session_id, approach_ids, class_factors,
                         replications, seed, confidence_level, tolerance_delay, tolerance_departures)
    if isinstance(result, JSONResponse):
        return result
    return _csv(validation_csv(result), "cruzamento-validacao.csv")


@router.post("/video/sessions/compare", response_model=SessionsCompareOut, responses=_errors, description=(
    "Compara duas sessões (por exemplo, manhã e tarde) lado a lado: ciclo, fases, taxa de chegada (teste binomial exato), ℓ, h e "
    "amarelo utilizável, a partir de duas respostas de /video/estimate. A tabela é descritiva: os p-valores não são corrigidos entre linhas."))
def video_sessions_compare(request: SessionsCompareRequest) -> dict:
    return _finite(compare_estimates(request.a, request.b, (request.label_a, request.label_b), request.confidence_level))


@router.post("/video/sessions/compare/export.csv", response_class=Response, responses={200: _CSV, **_errors})
def video_sessions_compare_csv(request: SessionsCompareRequest) -> Response:
    result = _finite(compare_estimates(request.a, request.b, (request.label_a, request.label_b), request.confidence_level))
    return _csv(sessions_csv(result), "cruzamento-sessoes.csv")
