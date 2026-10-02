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


# ---------- erros ----------

class FieldError(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    code: str       # unstable_system | invalid_parameter | insufficient_sample | invalid_request
    message: str
    fields: list[FieldError] | None = None
