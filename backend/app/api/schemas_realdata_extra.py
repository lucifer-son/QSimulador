"""Esquemas dos acréscimos da Fase 7: níveis de carga (RF-43), simulação, relatório (RF-44) e M/M/c//N."""

from typing import Literal

from pydantic import BaseModel, Field

from app.api.schemas import MetricSummaryOut, QueueReplicationOut
from app.api.schemas_realdata import AnalysisResponse, CompareRequest, LevelModel, MetricComparisonOut


class SimulationIn(BaseModel):
    simulation_time: float = Field(gt=0, description="Tempo simulado de cada réplica (s).")
    replications: int = Field(default=10, description="Réplicas independentes por nível.")
    warmup_time: float = Field(default=0.0, description="Aquecimento descartado (s).")
    seed: int | None = Field(default=None, description="Semente-base; o nível i usa semente-base + i.")
    confidence_level: float = Field(default=0.95, description="Nível de confiança dos intervalos.")


# ---------- níveis de carga (CSV agregado) ----------

class LevelSuggestionsOut(BaseModel):
    mu: float | None = Field(description="1/R no menor nível de carga (req/s).")
    mu_source: Literal["menor_nivel"]
    think_time: float | None = Field(description="Z = N/X − R no menor nível (s); null se não for positivo.")
    think_source: Literal["estimado"] | None
    base_users: int


class LevelsImportResponse(BaseModel):
    levels: list[LevelModel] = Field(description="No mesmo formato do `levels` de /analyze: alimentam /compare.")
    suggestions: LevelSuggestionsOut
    warnings: list[str]


# ---------- comparação com simulação ----------

class SimulatedCompareRequest(CompareRequest):
    simulation: SimulationIn


class SimulatedMetricOut(MetricComparisonOut):
    simulated_mean: float | None = None
    simulated_ci_low: float | None = None
    simulated_ci_high: float | None = None
    simulated_error_pct: float | None = Field(default=None, description="|simulação − observado| / observado × 100.")
    simulation_within_observed_ci: bool | None = None


class SimulatedLevelOut(BaseModel):
    users: int | None
    metrics: dict[str, SimulatedMetricOut]


class SimulationUsedOut(BaseModel):
    simulation_time: float
    replications: int
    warmup_time: float
    seed: int
    confidence_level: float


class SimulatedCompareResponse(BaseModel):
    notation: str
    comparison: list[SimulatedLevelOut]
    simulation: SimulationUsedOut | None = Field(default=None, description="Ausente na comparação só analítica.")


# ---------- relatório ----------

class ReportRequest(BaseModel):
    format: Literal["markdown", "html"] = "markdown"
    title: str = "Relatório experimental — QSimulador"
    analysis: AnalysisResponse | None = Field(default=None, description="Resultado de /analyze.")
    levels_import: LevelsImportResponse | None = Field(default=None, description="Resultado de /import/levels.")
    comparison: SimulatedCompareResponse | None = Field(
        default=None, description="Resultado de /compare ou /compare-simulated, se for outro modelo que o recomendado."
    )


class ReportResponse(BaseModel):
    format: Literal["markdown", "html"]
    filename: str
    media_type: str
    content: str


# ---------- M/M/c//N ----------

class FinitePopulationRequest(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"population": 10, "think_time": 1.0, "mu": 5.0, "servers": 1}]}}

    population: int = Field(description="N, número de usuários.")
    think_time: float = Field(description="Z, tempo médio de reflexão (s); 0 é permitido.")
    mu: float = Field(description="Taxa de serviço por servidor (req/s).")
    servers: int = Field(default=1, description="c, servidores (1 = M/M/1//N).")


class FinitePopulationSimulateRequest(FinitePopulationRequest):
    simulation_time: float = Field(gt=0)
    replications: int = 10
    warmup_time: float = 0.0
    seed: int | None = None
    confidence_level: float = 0.95


class FinitePopulationResponse(BaseModel):
    model: str
    population: int
    think_time: float
    servers: int
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    p0: float
    throughput: float
    p_wait: float
    p_block: float


class FinitePopulationSimulationResponse(BaseModel):
    model: str
    population: int
    think_time: float
    mu: float
    servers: int
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: list[QueueReplicationOut]
    summary: dict[str, MetricSummaryOut]
