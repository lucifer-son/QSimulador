"""Rotas da Fase 7: análise de dados reais (CSV do JMeter) e recomendação de modelo."""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from app.api.schemas import ErrorResponse
from app.api.schemas_realdata import (
    AnalysisResponse, CompareRequest, CompareResponse, LevelModel,
)
from app.domain.validation.errors import InvalidDatasetError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES, build_context
from app.realdata.jmeter import parse_jtl
from app.realdata.metrics import EmpiricalMetrics, LoadLevel
from app.realdata.recommendation import analyze, compare_chosen
from app.simulation.results import MetricSummary

router = APIRouter(prefix="/api/realdata", tags=["Dados reais"])

_errors = {
    422: {"model": ErrorResponse, "description": "Arquivo ou parâmetros inválidos"},
    413: {"model": ErrorResponse, "description": "Arquivo acima do limite"},
}


def _level(model: LevelModel) -> LoadLevel:
    data = model.metrics.model_dump()
    data["summaries"] = {k: MetricSummary(**v) for k, v in data["summaries"].items()}
    return LoadLevel(model.users, EmpiricalMetrics(**data))


def _read_csv(file: UploadFile) -> bytes | JSONResponse:
    name = (file.filename or "").lower()
    if not name.endswith(".csv"):
        raise InvalidDatasetError("Envie um arquivo com extensão .csv.", "file")
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        return JSONResponse(
            status_code=413,
            content={"code": "file_too_large", "message": f"O arquivo passa do limite de {mb} MB.",
                     "fields": [{"field": "file", "message": f"O arquivo passa do limite de {mb} MB."}]},
        )
    return content


# Rota síncrona (def) de propósito: a análise é CPU-bound e o FastAPI a executa em uma thread.
@router.post("/analyze", response_model=AnalysisResponse, responses=_errors)
def analyze_csv(
    file: Annotated[UploadFile, File(description="CSV (JTL) exportado pelo JMeter, com cabeçalho.")],
    system_type: Annotated[str, Form(description="auto, open ou closed.")] = "auto",
    servers: Annotated[int | None, Form(description="Número de servidores, se conhecido.")] = None,
    service_time_s: Annotated[float | None, Form(description="Tempo médio de serviço (s), se conhecido.")] = None,
    think_time_s: Annotated[float | None, Form(description="Tempo de reflexão Z (s), se conhecido.")] = None,
    capacity: Annotated[int | None, Form(description="Capacidade total K, se conhecida.")] = None,
    labels: Annotated[str | None, Form(description="Rótulos (label) a analisar, separados por vírgula.")] = None,
    trim_start_pct: Annotated[float, Form(description="% do início descartado (aquecimento).")] = 10.0,
    trim_end_pct: Annotated[float, Form(description="% do fim descartado (encerramento).")] = 10.0,
    confidence_level: Annotated[float, Form()] = 0.95,
):
    """Valida o CSV, calcula as métricas medidas, verifica os dados e recomenda o modelo de melhor ajuste."""
    content = _read_csv(file)
    if isinstance(content, JSONResponse):
        return content
    context = build_context(
        system_type=system_type, servers=servers, service_time_s=service_time_s,
        think_time_s=think_time_s, capacity=capacity,
        labels=[x.strip() for x in labels.split(",") if x.strip()] if labels else None,
        trim_start_pct=trim_start_pct, trim_end_pct=trim_end_pct, confidence_level=confidence_level,
    )
    return AnalysisResponse.model_validate(analyze(parse_jtl(content), context).as_dict())


@router.post("/compare", response_model=CompareResponse, responses=_errors)
def compare(request: CompareRequest) -> CompareResponse:
    """Compara as medições com o modelo escolhido pelo usuário, sem reenviar o arquivo."""
    notation, comparison = compare_chosen(
        request.model, [_level(lv) for lv in request.levels], request.mu,
        servers=request.servers, capacity=request.capacity, think_time=request.think_time,
    )
    return CompareResponse.model_validate({"notation": notation, "comparison": comparison})
