"""Esquemas (entrada e saída) da API."""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

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


class ReplicationOut(BaseModel):
    index: int
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
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
