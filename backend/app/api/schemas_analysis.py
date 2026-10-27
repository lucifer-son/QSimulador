"""Esquemas da Fase 13: distribuições (P(n), P(Wq > t)), sensibilidade Wq × λ e ajuste de amostras.

Todos os nomes de saída levam o prefixo `Analysis` (nomes genéricos colidiriam no OpenAPI).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from app.api.schemas import MetricSummaryOut
from app.api.schemas_service import ServiceOut, ServiceSpec

AnalysisModelKey = Literal["mm1", "mmc", "mm1k", "mmck", "mg1", "erlangb", "mgc"]


class AnalysisConfigIn(BaseModel):
    """A configuração do Laboratório (a mesma dos experimentos e do dimensionamento)."""

    model_config = ConfigDict(populate_by_name=True)

    model: AnalysisModelKey = Field(description="Modelo. O Erlang-B não tem fila e é recusado.")
    lam: StrictFloat = Field(alias="lambda", description="Taxa de chegada λ.")
    mu: StrictFloat | None = Field(default=None, description="Taxa de serviço μ. Obrigatória, exceto em mg1 e mgc (use `service`).")
    service: ServiceSpec | None = Field(default=None, description="Serviço do mg1 e do mgc.")
    servers: StrictInt | None = Field(default=None, description="c. Obrigatório em mmc, mmck e mgc.")
    capacity: StrictInt | None = Field(default=None, description="K. Obrigatório em mm1k e mmck.")


class AnalysisSimulationIn(BaseModel):
    simulation_time: StrictFloat | None = Field(default=None, description="T por réplica. Padrão: 20.000 chegadas esperadas (20.000/λ).")
    replications: StrictInt = Field(default=10, description="Réplicas (2 a 100).")
    warmup_time: StrictFloat | None = Field(default=None, description="Aquecimento descartado. Padrão: 10 % de T.")
    seed: StrictInt | None = Field(default=None, description="Semente (reproduz o resultado). Sem ela, uma é sorteada e devolvida.")
    confidence_level: StrictFloat = Field(default=0.95)


class AnalysisDistributionRequest(AnalysisConfigIn):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"examples": [{"model": "mmc", "lambda": 15, "mu": 10, "servers": 2}]},
    )

    points: StrictInt = Field(default=60, description="Pontos da curva P(Wq > t) (2 a 200).")
    t_max: StrictFloat | None = Field(default=None, description="Fim do eixo t da fórmula fechada. Padrão: até a cauda cair a 1e-4.")
    simulate: bool = Field(
        default=False,
        description="Simula também nos modelos com fórmula fechada (mm1 e mmc), para conferir. Nos demais é sempre simulado.",
    )
    simulation: AnalysisSimulationIn = Field(default_factory=AnalysisSimulationIn)


class AnalysisSensitivityRequest(AnalysisConfigIn):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"examples": [{"model": "mm1", "lambda": 8, "mu": 10}]},
    )

    span: StrictFloat = Field(default=0.5, description="Fração de λ para cada lado (0 a 0,95): a faixa vai de λ·(1 − span) a λ·(1 + span).")
    points: StrictInt = Field(default=41, description="Pontos da curva (3 a 200; a grade tem sempre um número ímpar).")


class AnalysisFitRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"sample": [0.8, 1.2, 0.5, 2.1, 0.9, 1.4, 0.7, 1.1, 3.0, 0.6], "kind": "service"}]})

    sample: list[float] = Field(description="Tempos positivos (serviço ou entre chegadas), de 10 até metade dos bytes do limite do envio de CSV.")
    kind: Literal["service", "interarrival"] = Field(default="service", description="O que a amostra representa (muda a sugestão de modelo).")
    bootstrap: StrictInt | None = Field(
        default=None,
        description="Réplicas do p-valor por Monte Carlo (20 a 2000) ou 0 para não calcular. Sem valor: 200, ou o que o teto de trabalho permite.",
    )
    alpha: StrictFloat = Field(default=0.05, description="Nível de significância da aderência.")
    seed: StrictInt | None = Field(default=None, description="Semente (reproduz o resultado). Sem ela, uma é sorteada e devolvida.")


# ---------- saída: distribuição ----------

class AnalysisStatesOut(BaseModel):
    model: str
    servers: int
    capacity: int | None
    states: list[int] = Field(description="Estados n mostrados, em ordem crescente.")
    p: list[float] = Field(description="P(N = n).")
    cumulative: list[float] = Field(description="P(N ≤ n) acumulado sobre os estados mostrados.")
    omitted_mass: float = Field(description="Massa fora dos estados mostrados (cauda da fila ilimitada ou trechos cortados).")
    p0: float
    mean: float = Field(description="L = E[N], exato.")
    rho: float
    p_wait: float
    p_block: float


class AnalysisWaitTailOut(BaseModel):
    model: str
    servers: int
    t: list[float]
    survival: list[float] = Field(description="P(Wq > t), fórmula fechada do M/M/c.")
    p_wait: float = Field(description="P(Wq > 0) = Erlang C.")
    decay_rate: float = Field(description="c·μ − λ: a cauda cai como exp(−taxa·t).")
    mean_wait: float
    percentiles: dict[str, float] = Field(description="p50, p90, p95 e p99 do tempo de espera.")


class AnalysisWaitSimulationOut(BaseModel):
    model: str
    servers: int
    capacity: int | None
    t: list[float]
    survival: list[MetricSummaryOut] = Field(description="P(Wq > t) em cada t: média entre réplicas e IC.")
    p_wait: MetricSummaryOut
    mean_wait: MetricSummaryOut
    p_block: MetricSummaryOut
    percentiles: dict[str, MetricSummaryOut]
    customers_per_replication: float
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float


class AnalysisDistributionResponse(BaseModel):
    model: str
    states: AnalysisStatesOut | None = Field(description="P(n) analítica; None no serviço geral (a aproximação só define as médias).")
    states_note: str | None
    wait_closed_form: AnalysisWaitTailOut | None = Field(description="Só no M/M/1 e M/M/c.")
    wait_simulation: AnalysisWaitSimulationOut | None = Field(description="Histograma da simulação (sempre, exceto no M/M/1 e M/M/c sem `simulate`).")
    wait_note: str | None


# ---------- saída: sensibilidade ----------

class AnalysisCurvePointOut(BaseModel):
    value: float = Field(description="λ.")
    status: Literal["ok", "unstable", "invalid"]
    message: str | None
    rho: float = Field(description="Utilização oferecida λ/(c·μ).")
    wq: float | None
    w: float | None
    lq: float | None


class AnalysisSensitivityResponse(BaseModel):
    model: str
    points: list[AnalysisCurvePointOut]
    current_index: int = Field(description="Posição do λ atual em `points`.")
    current: AnalysisCurvePointOut = Field(description="O ponto do Laboratório, calculado direto.")
    span: float
    stability_limit: float | None = Field(description="λ máximo mostrado por estabilidade (None com capacidade finita).")
    service: ServiceOut | None = None


# ---------- saída: ajuste ----------

class AnalysisFitCandidateOut(BaseModel):
    key: Literal["exponential", "erlang", "lognormal", "weibull", "uniform"]
    label: str
    parameters: dict[str, float]
    n_params: int
    loglik: float
    aic: float
    delta_aic: float | None = Field(description="AIC − menor AIC entre as comparáveis (None na uniforme).")
    akaike_weight: float | None
    comparable_aic: bool = Field(description="False na uniforme: o suporte depende da amostra.")
    mean: float
    cv: float
    ks_statistic: float
    p_value: float | None = Field(description="Aderência por Monte Carlo (bootstrap paramétrico); None sem bootstrap.")
    p_value_se: float | None = Field(description="Erro de Monte Carlo do p-valor.")
    adequate: bool | None = Field(description="p ≥ α; None sem bootstrap.")
    service: dict[str, float | str] | None = Field(description="Serviço equivalente no M/G/c.")
    notes: list[str]


class AnalysisModelSuggestionOut(BaseModel):
    model: Literal["M/M/c", "M/D/c", "M/G/c"] | None
    lab_model: Literal["mmc", "mgc"] | None
    distribution: str | None
    cv: float
    kind: Literal["service", "interarrival"]
    text: str


class AnalysisHistogramOut(BaseModel):
    edges: list[float]
    counts: list[int]
    density: list[float]


class AnalysisCurvesOut(BaseModel):
    t: list[float]
    pdf: dict[str, list[float]] = Field(description="Densidade de cada candidata nos pontos t.")


class AnalysisFitResultOut(BaseModel):
    kind: Literal["service", "interarrival"]
    n: int
    mean: float
    std: float
    cv: float
    cv_ci: list[float] | None = Field(description="IC de 95 % do CV (bootstrap não paramétrico).")
    minimum: float
    maximum: float
    degenerate: bool = Field(description="Amostra constante: não há ajuste, só a sugestão M/D/c.")
    bootstrap: int
    alpha: float
    seed: int
    candidates: list[AnalysisFitCandidateOut]
    best: str | None = Field(description="Menor AIC entre as comparáveis (a uniforme não entra).")
    adequate: list[str] = Field(description="Candidatas com p ≥ α.")
    none_adequate: bool | None = Field(description="True quando há p-valor e nenhuma candidata é adequada.")
    suggestion: AnalysisModelSuggestionOut
    service_suggestion: dict[str, float | str] | None = Field(description="Serviço do M/M/c, M/D/c ou M/G/c sugerido, no formato do Laboratório.")
    histogram: AnalysisHistogramOut
    curves: AnalysisCurvesOut
    warnings: list[str]


class AnalysisFitEventOut(BaseModel):
    """Uma linha do NDJSON. start → candidate (uma por candidata) → done; error encerra."""

    type: Literal["start", "candidate", "done", "error"]
    n: int | None = None
    bootstrap: int | None = None
    seed: int | None = None
    total: int | None = Field(default=None, description="Candidatas (para a barra de progresso).")
    completed: int | None = None
    candidate: AnalysisFitCandidateOut | None = None
    result: AnalysisFitResultOut | None = Field(default=None, description="Resultado completo, só em done.")
    code: str | None = None
    message: str | None = None
    field: str | None = None
