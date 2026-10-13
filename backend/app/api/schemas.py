"""Esquemas (entrada e saída) da API."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt

# Números estritos: aceitam int/float do JSON, mas rejeitam texto ("40") e
# booleanos, que o Pydantic converteria silenciosamente no modo padrão.
Rate = Annotated[StrictFloat, Field(description="Taxa média (ex.: req/s).")]


# ---------- entrada ----------

class MM1CalculateRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{"lambda": 40, "mu": 50}]})

    lam: Rate = Field(alias="lambda", description="Taxa média de chegada (λ).")
    mu: Rate = Field(description="Taxa média de serviço (μ).")


class MM1SimulateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "lambda": 40,
                    "mu": 50,
                    "simulation_time": 2000,
                    "replications": 10,
                    "warmup_time": 100,
                    "seed": 2026,
                }
            ]
        }
    )

    lam: Rate = Field(alias="lambda", description="Taxa média de chegada (λ).")
    mu: Rate = Field(description="Taxa média de serviço (μ).")
    simulation_time: StrictFloat = Field(description="Tempo simulado por replicação.")
    replications: StrictInt = Field(default=10, description="Número de replicações.")
    warmup_time: StrictFloat = Field(
        default=0.0, description="Período inicial descartado (transitório)."
    )
    seed: StrictInt | None = Field(
        default=None,
        description="Semente aleatória. Se omitida, uma é sorteada e devolvida.",
    )
    confidence_level: StrictFloat = Field(
        default=0.95, description="Nível do intervalo de confiança (0 a 1)."
    )


class MM1CompareRequest(MM1SimulateRequest):
    """Mesmos parâmetros da simulação: o analítico usa apenas λ e μ."""


# ---------- saída ----------

class MM1CalculateResponse(BaseModel):
    model: str = "M/M/1"
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    p0: float


class ReplicationOut(BaseModel):
    index: int
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    p0: float
    throughput: float
    measured_customers: int
    observation_time: float


class MetricSummaryOut(BaseModel):
    mean: float
    std: float | None
    ci_low: float | None
    ci_high: float | None
    n: int


class SimulationResponse(BaseModel):
    model: str = "M/M/1"
    lam: float = Field(alias="lambda")
    mu: float
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: list[ReplicationOut]
    summary: dict[str, MetricSummaryOut]


class MetricComparisonOut(BaseModel):
    analytical: float
    simulated_mean: float
    ci_low: float | None
    ci_high: float | None
    absolute_error: float
    relative_error_pct: float | None
    within_ci: bool | None


class ComparisonResponse(BaseModel):
    model: str = "M/M/1"
    lam: float = Field(alias="lambda")
    mu: float
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    metrics: dict[str, MetricComparisonOut]
    all_within_ci: bool | None
    max_relative_error_pct: float | None


# ---------- erros ----------

class FieldError(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    code: str       # unstable_system | invalid_parameter | insufficient_sample | invalid_request
    message: str
    fields: list[FieldError] | None = None


# ======================================================================
# M/M/c, M/M/1/K e M/M/c/K
# ======================================================================

# ---------- entrada ----------

class MMCCalculateRequest(MM1CalculateRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [{"lambda": 8, "mu": 1, "servers": 10}]})

    servers: StrictInt = Field(description="Número de servidores (c).")


class MMCSimulateRequest(MM1SimulateRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"lambda": 8, "mu": 1, "servers": 10, "simulation_time": 2000, "replications": 10,
                 "warmup_time": 100, "seed": 2026}
            ]
        }
    )

    servers: StrictInt = Field(description="Número de servidores (c).")


class MM1KCalculateRequest(MM1CalculateRequest):
    model_config = ConfigDict(json_schema_extra={"examples": [{"lambda": 12, "mu": 10, "capacity": 5}]})

    capacity: StrictInt = Field(description="Capacidade total do sistema, em clientes (K).")


class MM1KSimulateRequest(MM1SimulateRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"lambda": 12, "mu": 10, "capacity": 5, "simulation_time": 2000, "replications": 10,
                 "warmup_time": 100, "seed": 2026}
            ]
        }
    )

    capacity: StrictInt = Field(description="Capacidade total do sistema, em clientes (K).")


class MMCKCalculateRequest(MM1CalculateRequest):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"lambda": 25, "mu": 10, "servers": 3, "capacity": 6}]}
    )

    servers: StrictInt = Field(description="Número de servidores (c).")
    capacity: StrictInt = Field(
        description="Capacidade total do sistema (K), incluindo os clientes em atendimento. Deve ser ≥ servers."
    )


class MMCKSimulateRequest(MM1SimulateRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"lambda": 25, "mu": 10, "servers": 3, "capacity": 6, "simulation_time": 2000,
                 "replications": 10, "warmup_time": 100, "seed": 2026}
            ]
        }
    )

    servers: StrictInt = Field(description="Número de servidores (c).")
    capacity: StrictInt = Field(
        description="Capacidade total do sistema (K), incluindo os clientes em atendimento. Deve ser ≥ servers."
    )


# ---------- saída ----------

class QueueCalculateResponse(BaseModel):
    model: str
    servers: int
    capacity: int | None
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    p0: float
    throughput: float
    p_wait: float
    p_block: float


class QueueReplicationOut(BaseModel):
    index: int
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    p0: float
    throughput: float
    p_wait: float
    p_block: float
    measured_customers: int
    observation_time: float


class QueueSimulationResponse(BaseModel):
    model: str
    lam: float = Field(alias="lambda")
    mu: float
    servers: int
    capacity: int | None
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: list[QueueReplicationOut]
    summary: dict[str, MetricSummaryOut]


class QueueComparisonResponse(BaseModel):
    model: str
    lam: float = Field(alias="lambda")
    mu: float
    servers: int
    capacity: int | None
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    metrics: dict[str, MetricComparisonOut]
    all_within_ci: bool | None
    max_relative_error_pct: float | None


# ======================================================================
# Fase 6: Experimentos (varredura, comparação de servidores e sensibilidade)
# ======================================================================

ModelKey = Literal["mm1", "mmc", "mm1k", "mmck"]
SweepVariable = Literal["lambda", "mu", "servers", "capacity"]
PointStatus = Literal["ok", "unstable", "invalid"]

_MODEL_DESCRIPTION = "Modelo: mm1, mmc, mm1k ou mmck (as mesmas chaves das rotas /api/models)."
_FIXED_NOTE = "Obrigatório para o modelo, a menos que seja o parâmetro varrido (então é ignorado)."


# ---------- entrada ----------

class SweepRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"model": "mm1", "variable": "lambda", "start": 10, "end": 45, "step": 5, "mu": 50},
                {"model": "mmck", "variable": "lambda", "start": 5, "end": 40, "step": 5,
                 "mu": 10, "servers": 3, "capacity": 6,
                 "simulate": True, "simulation_time": 500, "replications": 5, "seed": 2026},
            ]
        }
    )

    model: ModelKey = Field(description=_MODEL_DESCRIPTION)
    variable: SweepVariable = Field(description="Parâmetro varrido (servers e capacity só nos modelos que os têm).")
    start: StrictFloat = Field(description="Primeiro valor da faixa.")
    end: StrictFloat = Field(description="Último valor da faixa (incluído quando start + n·step = end).")
    step: StrictFloat = Field(description="Incremento entre os pontos (maior que zero; inteiro para servers e capacity).")
    lam: StrictFloat | None = Field(default=None, alias="lambda", description="Taxa de chegada (λ). " + _FIXED_NOTE)
    mu: StrictFloat | None = Field(default=None, description="Taxa de serviço (μ). " + _FIXED_NOTE)
    servers: StrictInt | None = Field(default=None, description="Servidores (c). " + _FIXED_NOTE)
    capacity: StrictInt | None = Field(default=None, description="Capacidade total (K). " + _FIXED_NOTE)
    simulate: StrictBool = Field(
        default=False, description="Se verdadeiro, simula também cada ponto estável (exige simulation_time)."
    )
    simulation_time: StrictFloat | None = Field(default=None, description="Tempo simulado por replicação, em cada ponto.")
    replications: StrictInt = Field(default=10, description="Número de replicações por ponto.")
    warmup_time: StrictFloat = Field(default=0.0, description="Período inicial descartado.")
    seed: StrictInt | None = Field(
        default=None,
        description="Semente aleatória, a mesma em todos os pontos. Se omitida, uma é sorteada e devolvida.",
    )
    confidence_level: StrictFloat = Field(default=0.95, description="Nível do intervalo de confiança (0 a 1).")


class ServerComparisonRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"servers_list": [1, 2, 3], "mu": 10, "start": 5, "end": 30, "step": 5}]
        }
    )

    servers_list: list[StrictInt] = Field(description="Números de servidores a comparar (de 2 a 8 valores distintos).")
    mu: StrictFloat = Field(description="Taxa de serviço de cada servidor (μ).")
    capacity: StrictInt | None = Field(
        default=None, description="Capacidade total (K). Se omitida, a fila é ilimitada (M/M/c)."
    )
    start: StrictFloat = Field(description="Primeiro valor de λ.")
    end: StrictFloat = Field(description="Último valor de λ.")
    step: StrictFloat = Field(description="Incremento de λ entre os pontos.")


class SensitivityRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [{"model": "mmck", "lambda": 25, "mu": 10, "servers": 3, "capacity": 6, "delta_pct": 10}]
        }
    )

    model: ModelKey = Field(description=_MODEL_DESCRIPTION)
    lam: StrictFloat = Field(alias="lambda", description="Taxa média de chegada (λ) do ponto base.")
    mu: StrictFloat = Field(description="Taxa média de serviço (μ) do ponto base.")
    servers: StrictInt | None = Field(default=None, description="Servidores (c). Obrigatório em mmc e mmck.")
    capacity: StrictInt | None = Field(default=None, description="Capacidade total (K). Obrigatório em mm1k e mmck.")
    delta_pct: StrictFloat = Field(
        default=10.0,
        description="Perturbação de λ e μ, em % (maior que 0 e até 50). c e K variam ±1 unidade.",
    )


# ---------- saída ----------

class SweepSimulationOut(BaseModel):
    simulation_time: float
    replications: int
    warmup_time: float
    seed: int
    confidence_level: float


class SweepPointOut(BaseModel):
    value: float = Field(description="Valor do parâmetro varrido neste ponto.")
    status: PointStatus = Field(description="ok, unstable (fora do regime estacionário) ou invalid (fora do domínio do modelo).")
    message: str | None = Field(description="Motivo do status, ou aviso da simulação do ponto.")
    offered_utilization: float = Field(description="Carga oferecida por servidor, λ/(c·μ). Em 1 ou mais, a fila ilimitada é instável.")
    metrics: dict[str, float] | None = Field(description="Métricas analíticas (nulo se o ponto não é válido).")
    simulation: dict[str, MetricSummaryOut] | None = Field(description="Resumo da simulação por métrica (só com simulate).")


class SweepResponse(BaseModel):
    model: str
    variable: str
    fixed: dict[str, float] = Field(description="Parâmetros mantidos fixos, com os nomes da API.")
    points: list[SweepPointOut]
    simulation: SweepSimulationOut | None = Field(description="Configuração efetiva da simulação, com a semente usada.")


class ServerSeriesOut(BaseModel):
    servers: int
    points: list[SweepPointOut]


class ServerComparisonResponse(BaseModel):
    model: str = Field(description="mmc (fila ilimitada) ou mmck (capacidade finita).")
    mu: float
    capacity: int | None
    series: list[ServerSeriesOut]


class SensitivitySideOut(BaseModel):
    value: float
    status: PointStatus
    message: str | None
    metrics: dict[str, float] | None


class MetricEffectOut(BaseModel):
    low_change_pct: float | None = Field(description="Variação % da métrica quando o parâmetro diminui.")
    high_change_pct: float | None = Field(description="Variação % da métrica quando o parâmetro aumenta.")
    elasticity: float | None = Field(description="Variação % da métrica para 1% de variação do parâmetro (nulo se um lado é inválido).")


class ParameterSensitivityOut(BaseModel):
    name: SweepVariable
    base_value: float
    perturbation: Literal["percent", "units"] = Field(description="percent (λ e μ) ou units (c e K, ±1).")
    low: SensitivitySideOut
    high: SensitivitySideOut
    effects: dict[str, MetricEffectOut]


class SensitivityResponse(BaseModel):
    model: str
    delta_pct: float
    base: dict[str, float]
    base_metrics: dict[str, float]
    parameters: list[ParameterSensitivityOut]
