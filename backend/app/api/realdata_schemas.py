"""Esquemas (entrada e saída) da API de dados reais (Fase 7)."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt, StrictStr

from app.api.schemas import MetricSummaryOut, ReplicationOut

Positive = Annotated[StrictFloat, Field(description="Número real positivo.")]


# ---------- entrada ----------

class ImportJMeterRequest(BaseModel):
    filename: StrictStr = Field(description="Nome do arquivo (deve terminar em .csv).")
    content: StrictStr = Field(description="Conteúdo do CSV do JMeter (até 10 MB).")
    label: StrictStr | None = Field(default=None, description="Analisa só este rótulo (padrão: todos).")
    trim_start_s: StrictFloat = Field(default=0.0, description="Segundos descartados no início (ramp-up).")
    trim_end_s: StrictFloat = Field(default=0.0, description="Segundos descartados no fim (ramp-down).")
    include_failures: StrictBool = Field(default=False, description="Inclui amostras com falha nas métricas.")


class ImportLevelsRequest(BaseModel):
    filename: StrictStr
    content: StrictStr = Field(description="CSV com users, avg_ms, throughput (e opcionais p90_ms, error_rate).")


class RealSimulationIn(BaseModel):
    simulation_time: Positive
    replications: StrictInt = 10
    warmup_time: StrictFloat = 0.0
    seed: StrictInt | None = None
    confidence_level: StrictFloat = 0.95


class MeasuredIn(BaseModel):
    throughput: Positive = Field(description="Vazão medida (req/s).")
    mean_response_ms: Positive = Field(description="Tempo médio de resposta medido (ms).")


MuSource = Literal["informed", "inverse_response", "baseline"]


class RealCompareRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "measured": {"throughput": 40, "mean_response_ms": 60}, "mode": "closed",
        "mu": 50, "servers": 1, "users": 10,
        "simulation": {"simulation_time": 1000, "replications": 5, "warmup_time": 50, "seed": 1},
    }]})

    measured: MeasuredIn
    mode: Literal["open", "closed"] = Field(description="Sistema aberto (M/M/c) ou fechado (M/M/c//N).")
    mu: Positive = Field(description="Taxa de serviço por servidor (req/s).")
    mu_source: MuSource = Field(default="informed", description="De onde veio μ (só para o relatório e os avisos).")
    servers: StrictInt = 1
    users: StrictInt | None = Field(default=None, description="N, obrigatório no modo fechado.")
    think_time: Positive | None = Field(default=None, description="Z em s; se omitido, vem de Z = N/X − R.")
    simulation: RealSimulationIn | None = Field(default=None, description="Se omitido, só o analítico.")


class LevelIn(BaseModel):
    users: StrictInt
    avg_ms: Positive
    throughput: Positive
    p90_ms: StrictFloat | None = None
    error_rate: StrictFloat | None = None


class LevelsCompareRequest(BaseModel):
    levels: Annotated[list[LevelIn], Field(min_length=1, max_length=50)]
    servers: StrictInt = 1
    mu: Positive | None = Field(default=None, description="Se omitido, μ = 1/R no menor nível.")
    think_time: Positive | None = Field(default=None, description="Se omitido, Z = N/X − R no menor nível.")
    simulation: RealSimulationIn | None = None


# ---------- saída ----------

class LabelSummaryOut(BaseModel):
    label: str
    samples: int
    mean_ms: float
    p90_ms: float
    error_rate: float


class DatasetSummaryOut(BaseModel):
    samples_total: int
    samples_used: int
    label: str | None
    include_failures: bool
    trim_start_s: float
    trim_end_s: float
    window_seconds: float
    throughput: float
    mean_ms: float
    std_ms: float
    min_ms: float
    max_ms: float
    p50_ms: float
    p90_ms: float
    p95_ms: float
    p99_ms: float
    error_rate: float
    users: int | None
    users_max: int | None
    suggested_mu: float
    labels: list[LabelSummaryOut]


class LevelOut(BaseModel):
    users: int
    avg_ms: float
    throughput: float
    p90_ms: float | None
    error_rate: float | None


class LevelsDatasetOut(BaseModel):
    levels: list[LevelOut]


class RealMetricOut(BaseModel):
    measured: float
    analytical: float
    analytical_error_pct: float | None
    simulated_mean: float | None
    ci_low: float | None
    ci_high: float | None
    simulated_error_pct: float | None
    measured_within_ci: bool | None
    role: Literal["prediction", "input"]
    measured_derived: bool


class RealSimulationOut(BaseModel):
    simulation_time: float
    replications: int
    warmup_time: float
    seed: int | None
    confidence_level: float


class RealCompareResponse(BaseModel):
    mode: Literal["open", "closed"]
    model: str
    mu: float
    mu_source: MuSource
    servers: int
    users: int | None
    think_time: float | None
    think_time_source: Literal["informed", "interactive_law"] | None
    arrival_rate: float | None
    metrics: dict[str, RealMetricOut]
    simulation: RealSimulationOut | None
    warnings: list[str]


class LevelComparisonOut(BaseModel):
    users: int
    measured_throughput: float
    measured_response_s: float
    throughput: RealMetricOut
    W: RealMetricOut


class LevelsCompareResponse(BaseModel):
    model: str
    servers: int
    mu: float
    mu_source: MuSource
    think_time: float
    think_time_source: Literal["informed", "interactive_law"]
    calibration_users: int | None
    levels: list[LevelComparisonOut]
    simulation: RealSimulationOut | None
    warnings: list[str]


class ReportRequest(BaseModel):
    format: Literal["markdown", "html"] = "markdown"
    title: StrictStr = "Relatório experimental — QSimulador"
    dataset: DatasetSummaryOut | None = None
    comparison: RealCompareResponse | None = None
    levels_comparison: LevelsCompareResponse | None = None


class ReportResponse(BaseModel):
    format: Literal["markdown", "html"]
    filename: str
    media_type: str
    content: str


# ---------- modelo fechado M/M/c//N ----------

class ClosedCalculateRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"users": 10, "think_time": 1.0, "mu": 5}]})

    users: StrictInt = Field(description="N, número de usuários.")
    think_time: Positive = Field(description="Z, tempo médio de reflexão (s).")
    mu: Positive = Field(description="Taxa de serviço por servidor.")
    servers: StrictInt = Field(default=1, description="c, servidores (1 = M/M/1//N).")


class ClosedSimulateRequest(ClosedCalculateRequest):
    simulation_time: Positive
    replications: StrictInt = 10
    warmup_time: StrictFloat = 0.0
    seed: StrictInt | None = None
    confidence_level: StrictFloat = 0.95


class ClosedCalculateResponse(BaseModel):
    model: str
    users: int
    think_time: float
    servers: int
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    p0: float
    throughput: float


class ClosedSimulationResponse(BaseModel):
    model: str
    users: int
    think_time: float
    mu: float
    servers: int
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: list[ReplicationOut]
    summary: dict[str, MetricSummaryOut]
