"""Esquemas da API de dados reais (Fase 7)."""

from typing import Literal

from pydantic import BaseModel, Field


class SummaryOut(BaseModel):
    mean: float | None
    std: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n: int


class EmpiricalMetricsModel(BaseModel):
    """Métricas medidas em uma janela (segundos e req/s)."""

    window_start: float
    window_end: float
    duration: float
    samples: int
    successes: int
    rejections: int
    other_failures: int
    arrival_rate: float = Field(description="λ̂: requisições iniciadas por segundo (inclui rejeitadas).")
    throughput: float = Field(description="X̂: respostas bem-sucedidas por segundo.")
    mean_response: float = Field(description="W̄: tempo médio de resposta (s).")
    p50: float | None = None
    p90: float | None = None
    p95: float | None = None
    p99: float | None = None
    mean_in_flight: float = Field(description="L̂: requisições em andamento, em média.")
    peak_in_flight: int
    mean_users: float | None = Field(default=None, description="N̄: usuários ativos (allThreads).")
    think_time: float | None = Field(default=None, description="Ẑ = N̄/X̂ − W̄ (s).")
    p_block: float
    p_error: float
    arrival_cv: float | None = None
    response_cv: float | None = None
    summaries: dict[str, SummaryOut]


class LevelModel(BaseModel):
    users: int | None = Field(description="Usuários do patamar de carga (null se o arquivo não tem allThreads).")
    metrics: EmpiricalMetricsModel


class DiagnosticOut(BaseModel):
    id: str
    title: str
    status: Literal["ok", "atencao", "critico", "info"]
    evidence: str


class EstimatesOut(BaseModel):
    mu: float | None = Field(description="null = não identificável (resultado autoconsistente).")
    mu_source: Literal["informado", "menor_nivel", "autoconsistente"]
    servers: int
    servers_source: Literal["informado", "estimado", "assumido"]
    think_time: float | None = None
    think_source: Literal["informado", "estimado"] | None = None
    capacity: int | None = None
    capacity_source: Literal["informado", "estimado"] | None = None
    notes: list[str]
    autoconsistent: bool


class ModelPickOut(BaseModel):
    key: str
    notation: str
    score_pct: float | None
    mu: float | None
    servers: int
    capacity: int | None = None
    population: int | None = None
    think_time: float | None = None


class CriterionOut(BaseModel):
    id: Literal["estrutura", "capacidade", "servidores", "dados", "estabilidade", "calibracao", "previsao"]
    passed: bool
    reason: str


class RankingOut(BaseModel):
    key: str
    notation: str
    eligible: bool
    score_pct: float | None = Field(description="Erro relativo médio (%) nas métricas de validação, mais penalidade por parâmetro.")
    scored_metrics: int
    mu: float | None
    recommended: bool
    reasons: list[str]
    error_pct: float | None = Field(default=None, description="Erro relativo médio (%) nas métricas de validação.")
    penalty_pp: float = Field(default=0.0, description="Penalidade de parcimônia (pontos percentuais).")
    criteria: list[CriterionOut]


class MetricComparisonOut(BaseModel):
    model: float
    observed: float
    observed_ci_low: float | None = None
    observed_ci_high: float | None = None
    absolute_error: float
    relative_error_pct: float | None = Field(description="|modelo − observado| / observado × 100.")
    model_within_observed_ci: bool | None = None


class LevelComparisonOut(BaseModel):
    users: int | None
    metrics: dict[str, MetricComparisonOut]


class DatasetOut(BaseModel):
    rows: int
    rows_analyzed: int
    labels: list[str]
    start: float
    end: float


class AnalysisServiceHintOut(BaseModel):
    """Sugestão de modelo pelo CV (Fase 13). Indicação, não parte do ranking."""

    model: Literal["M/M/c", "M/D/c", "M/G/c"] | None = Field(description="Modelo sugerido pelo CV; None se não há (chegadas).")
    lab_model: Literal["mmc", "mgc"] | None = Field(description="Modelo do Laboratório para c ≥ 2.")
    distribution: str | None = Field(description="\"deterministic\" no M/D/c; nos demais, quem escolhe é o ajuste.")
    cv: float
    kind: Literal["service", "interarrival"]
    text: str
    basis: str = Field(description="De onde veio o CV (nível de carga e ressalva).")


class AnalysisResponse(BaseModel):
    status: Literal["recommended", "no_good_fit"]
    confidence: Literal["alta", "media", "baixa"]
    recommended: ModelPickOut | None
    nearest: ModelPickOut | None
    ranking: list[RankingOut]
    rationale: str
    warnings: list[str]
    diagnostics: list[DiagnosticOut]
    system_type: Literal["open", "closed"]
    estimates: EstimatesOut
    overall: EmpiricalMetricsModel
    levels: list[LevelModel]
    comparison: list[LevelComparisonOut]
    dataset: DatasetOut
    service_hint: AnalysisServiceHintOut | None = Field(
        default=None, description="Sugestão M/M/c, M/D/c ou M/G/c pelo CV do menor nível de carga (não altera o ranking).")


class CompareRequest(BaseModel):
    model_config = {"json_schema_extra": {"examples": [{"model": "mm1n", "mu": 10.0, "servers": 1, "think_time": 1.0, "levels": []}]}}

    model: Literal["mm1", "mmc", "mm1k", "mmck", "mm1n", "mmcn"]
    mu: float = Field(gt=0, description="Taxa de serviço por servidor (req/s).")
    servers: int = 1
    capacity: int | None = None
    think_time: float | None = None
    levels: list[LevelModel] = Field(description="Os níveis devolvidos por /analyze.")


class CompareResponse(BaseModel):
    notation: str
    comparison: list[LevelComparisonOut]
