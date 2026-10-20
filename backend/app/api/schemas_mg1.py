"""Esquemas da API do serviço geral (Fase 9: M/D/1 e M/G/1)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from app.api.schemas import MetricComparisonOut, MetricSummaryOut, ReplicationOut
from app.api.schemas_service import DistributionKey, ServiceOut, ServiceSpec  # noqa: F401

# ---------- entrada ----------

class MG1CalculateRequest(ServiceSpec):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"lambda": 25, "distribution": "lognormal", "mean": 0.02, "cv": 0.5},
                {"lambda": 40, "distribution": "deterministic", "mu": 80},
            ]
        },
    )

    lam: StrictFloat = Field(alias="lambda", description="Taxa média de chegada (λ).")


class MG1SimulateRequest(MG1CalculateRequest):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"lambda": 25, "distribution": "lognormal", "mean": 0.02, "cv": 0.5,
                 "simulation_time": 2000, "replications": 10, "warmup_time": 100, "seed": 2026}
            ]
        },
    )

    simulation_time: StrictFloat = Field(description="Tempo simulado por replicação.")
    replications: StrictInt = Field(default=10, description="Número de replicações.")
    warmup_time: StrictFloat = Field(default=0.0, description="Período inicial descartado (transitório).")
    seed: StrictInt | None = Field(default=None, description="Semente aleatória. Se omitida, uma é sorteada e devolvida.")
    confidence_level: StrictFloat = Field(default=0.95, description="Nível do intervalo de confiança (0 a 1).")


# ---------- saída ----------

class MG1CalculateResponse(BaseModel):
    model: str
    service: ServiceOut
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    p0: float


class MG1SimulationResponse(BaseModel):
    model: str
    lam: float = Field(alias="lambda")
    service: ServiceOut
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: list[ReplicationOut]
    summary: dict[str, MetricSummaryOut]


class MG1ComparisonResponse(BaseModel):
    model: str
    lam: float = Field(alias="lambda")
    service: ServiceOut
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    metrics: dict[str, MetricComparisonOut]
    all_within_ci: bool | None
    max_relative_error_pct: float | None


class ParameterOut(BaseModel):
    name: str = Field(description="Nome do campo na API.")
    label: str
    kind: Literal["float", "int"]
    description: str


class DistributionOut(BaseModel):
    key: str
    label: str
    description: str
    accepts_mean: bool = Field(description="Se verdadeiro, informe mean ou mu (média ou taxa de serviço).")
    parameters: list[ParameterOut] = Field(description="Parâmetros próprios, além de mean/mu.")
    example: dict[str, int | float] = Field(description="Exemplo válido de parâmetros (aceito pelas rotas do M/G/1).")


class DistributionCatalogResponse(BaseModel):
    distributions: list[DistributionOut]
