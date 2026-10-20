"""Esquemas da API da Fase 10: Erlang-B (M/M/c/c) e M/G/c (Allen–Cunneen)."""

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from app.api.schemas import (
    MetricComparisonOut,
    MetricSummaryOut,
    MMCCalculateRequest,
    MMCSimulateRequest,
    QueueCalculateResponse,
    QueueReplicationOut,
)
from app.api.schemas_service import ServiceOut, ServiceSpec

# ======================================================================
# Erlang-B
# ======================================================================

_ERLANGB_NOTE = "Sistema de perda: sem fila, a capacidade total é igual ao número de servidores."


class ErlangBCalculateRequest(MMCCalculateRequest):
    model_config = ConfigDict(
        json_schema_extra={"examples": [{"lambda": 20, "mu": 1, "servers": 15}]},
    )


class ErlangBSimulateRequest(MMCSimulateRequest):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {"lambda": 20, "mu": 1, "servers": 15, "simulation_time": 2000, "replications": 10,
                 "warmup_time": 100, "seed": 2026}
            ]
        }
    )


class ErlangBSizeRequest(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={"examples": [{"lambda": 20, "mu": 1, "target_blocking": 0.01}]},
    )

    lam: StrictFloat = Field(alias="lambda", description="Taxa média de chegada (λ).")
    mu: StrictFloat = Field(description="Taxa média de serviço de cada servidor (μ).")
    target_blocking: StrictFloat = Field(description="Bloqueio máximo aceitável, entre 0 e 1 (ex.: 0,01 = 1%).")


class ErlangBCalculateResponse(QueueCalculateResponse):
    offered_load: float = Field(description="Tráfego oferecido a = λ/μ, em Erlangs.")
    carried_load: float = Field(description="Tráfego carregado a·(1 − B): servidores ocupados em média.")
    lost_rate: float = Field(description="Chegadas perdidas por unidade de tempo, λ·B.")


class ErlangBSizeResponse(BaseModel):
    target_blocking: float
    servers: int = Field(description="Menor número de servidores com bloqueio ≤ alvo.")
    blocking: float = Field(description="Bloqueio B(c, a) com esse número de servidores.")
    blocking_previous: float | None = Field(description="Bloqueio com um servidor a menos (nulo se c = 1).")
    offered_load: float
    carried_load: float
    rho: float
    lost_rate: float


# ======================================================================
# M/G/c
# ======================================================================

_APPROX = (
    "Aproximação de Allen–Cunneen: exata com c = 1 (Pollaczek-Khinchine) ou serviço exponencial; "
    "nos demais casos, aproximada (veja `exact` e `warnings`)."
)


class MGCCalculateRequest(ServiceSpec):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"lambda": 80, "servers": 10, "distribution": "lognormal", "mean": 0.1, "cv": 1.5},
                {"lambda": 80, "servers": 10, "distribution": "deterministic", "mean": 0.1},
            ]
        },
    )

    lam: StrictFloat = Field(alias="lambda", description="Taxa média de chegada (λ).")
    servers: StrictInt = Field(description="Número de servidores (c).")


class MGCSimulateRequest(MGCCalculateRequest):
    model_config = ConfigDict(
        populate_by_name=True,
        json_schema_extra={
            "examples": [
                {"lambda": 80, "servers": 10, "distribution": "lognormal", "mean": 0.1, "cv": 1.5,
                 "simulation_time": 2000, "replications": 10, "warmup_time": 100, "seed": 2026}
            ]
        },
    )

    simulation_time: StrictFloat = Field(description="Tempo simulado por replicação.")
    replications: StrictInt = Field(default=10, description="Número de replicações.")
    warmup_time: StrictFloat = Field(default=0.0, description="Período inicial descartado (transitório).")
    seed: StrictInt | None = Field(default=None, description="Semente aleatória. Se omitida, uma é sorteada e devolvida.")
    confidence_level: StrictFloat = Field(default=0.95, description="Nível do intervalo de confiança (0 a 1).")


class MGCCalculateResponse(BaseModel):
    model: str
    servers: int
    service: ServiceOut
    exact: bool = Field(description="Verdadeiro quando a aproximação coincide com o resultado exato (c = 1 ou CV = 1).")
    warnings: list[str] = Field(description="Avisos de faixa de validade da aproximação (vazio se está em faixa segura).")
    rho: float
    L: float
    Lq: float
    W: float
    Wq: float
    throughput: float
    p_wait: float = Field(description="Probabilidade de esperar (Erlang C).")


class MGCSimulationResponse(BaseModel):
    model: str
    lam: float = Field(alias="lambda")
    servers: int
    service: ServiceOut
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    runs: list[QueueReplicationOut]
    summary: dict[str, MetricSummaryOut]


class MGCComparisonResponse(BaseModel):
    model: str
    lam: float = Field(alias="lambda")
    servers: int
    service: ServiceOut
    exact: bool
    warnings: list[str]
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    metrics: dict[str, MetricComparisonOut]
    all_within_ci: bool | None
    max_relative_error_pct: float | None
