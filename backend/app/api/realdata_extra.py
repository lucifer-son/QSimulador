"""Acréscimos da Fase 7 em /api/realdata: níveis de carga (RF-43), comparação com simulação e relatório (RF-44).

As rotas /analyze e /compare ficam em `realdata.py` e não são alteradas aqui.
"""

from typing import Annotated

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import JSONResponse

from app.api.realdata import _level
from app.api.schemas import ErrorResponse
from app.api.schemas_realdata_extra import (
    LevelsImportResponse, ReportRequest, ReportResponse, SimulatedCompareRequest, SimulatedCompareResponse,
)
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES
from app.realdata.levels import parse_levels
from app.realdata.report import build_report
from app.realdata.simulated import SimulationSettings, compare_simulated

router = APIRouter(prefix="/api/realdata", tags=["Dados reais"])

_errors = {
    422: {"model": ErrorResponse, "description": "Arquivo ou parâmetros inválidos"},
    413: {"model": ErrorResponse, "description": "Arquivo acima do limite"},
}


@router.post("/import/levels", response_model=LevelsImportResponse, responses=_errors)
def import_levels(
    file: Annotated[UploadFile, File(description="CSV com users, avg_ms, throughput (e opcionais p90_ms, error_rate).")],
):
    """Importa o CSV agregado por nível de carga e devolve os níveis (para /compare) e a calibração sugerida."""
    name = file.filename or ""
    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        mb = MAX_UPLOAD_BYTES // (1024 * 1024)
        message = f"O arquivo passa do limite de {mb} MB."
        return JSONResponse(
            status_code=413,
            content={"code": "file_too_large", "message": message, "fields": [{"field": "file", "message": message}]},
        )
    imported = parse_levels(name, content)
    return LevelsImportResponse.model_validate({
        "levels": [
            {"users": lv.users, "metrics": lv.metrics.as_dict()} for lv in imported.levels
        ],
        "suggestions": imported.suggestions.__dict__,
        "warnings": imported.warnings,
    })


# Rota síncrona (def) de propósito: a simulação é CPU-bound e roda em thread.
@router.post("/compare-simulated", response_model=SimulatedCompareResponse, responses=_errors)
def compare_with_simulation(request: SimulatedCompareRequest) -> SimulatedCompareResponse:
    """Como /compare, mais a média simulada (com IC) de cada métrica em cada nível: medido × analítico × simulação."""
    sim = request.simulation
    notation, comparison, used = compare_simulated(
        request.model, [_level(lv) for lv in request.levels], request.mu,
        SimulationSettings(sim.simulation_time, sim.replications, sim.warmup_time, sim.seed, sim.confidence_level),
        servers=request.servers, capacity=request.capacity, think_time=request.think_time,
    )
    return SimulatedCompareResponse.model_validate({"notation": notation, "comparison": comparison, "simulation": used})


@router.post("/report", response_model=ReportResponse, responses=_errors)
def report(request: ReportRequest) -> ReportResponse:
    """Gera o relatório experimental (Markdown ou HTML) a partir dos resultados já calculados."""
    if not (request.analysis or request.levels_import or request.comparison):
        raise QueueValidationError("Informe ao menos um de: analysis, levels_import, comparison.", "analysis")
    content = build_report(
        request.format, request.title,
        request.analysis.model_dump() if request.analysis else None,
        request.levels_import.model_dump() if request.levels_import else None,
        request.comparison.model_dump() if request.comparison else None,
    )
    ext, media = ("md", "text/markdown") if request.format == "markdown" else ("html", "text/html")
    return ReportResponse(
        format=request.format, filename=f"relatorio-experimental.{ext}",
        media_type=f"{media}; charset=utf-8", content=content,
    )
