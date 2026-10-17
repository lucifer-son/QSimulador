"""Esquemas da API do serviço geral (Fase 9: M/D/1 e M/G/1)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

from app.api.schemas import MetricComparisonOut, MetricSummaryOut, ReplicationOut

DistributionKey = Literal[
    "deterministic", "exponential", "erlang", "lognormal", "weibull",
    "uniform", "triangular", "truncated_normal",
]

_UNUSED = " Ignorado pelas distribuições que não usam este parâmetro."


# ---------- entrada ----------

class MG1CalculateRequest(BaseModel):
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
    distribution: DistributionKey = Field(description="Distribuição do tempo de serviço (veja GET /api/distributions).")
    mean: StrictFloat | None = Field(
        default=None, description="Tempo médio de serviço E[S] (exponencial, determinística, Erlang-k, lognormal, Weibull)."
    )
    mu: StrictFloat | None = Field(
        default=None, description="Alternativa à média: taxa de serviço μ = 1/E[S]. Informe mean ou mu, não os dois."
    )
    k: StrictInt | None = Field(default=None, description="Etapas do Erlang-k (inteiro ≥ 1)." + _UNUSED)
    cv: StrictFloat | None = Field(default=None, description="Coeficiente de variação (lognormal e Weibull)." + _UNUSED)
    min_value: StrictFloat | None = Field(default=None, alias="min", description="Mínimo (uniforme e triangular)." + _UNUSED)
    mode: StrictFloat | None = Field(default=None, description="Moda (triangular)." + _UNUSED)
    max_value: StrictFloat | None = Field(default=None, alias="max", description="Máximo (uniforme e triangular)." + _UNUSED)
    loc: StrictFloat | None = Field(default=None, description="Média da normal original (normal truncada em 0)." + _UNUSED)
    scale: StrictFloat | None = Field(default=None, description="Desvio padrão da normal original (normal truncada em 0)." + _UNUSED)

    def service_values(self) -> dict[str, float | int]:
        """Parâmetros do serviço informados, com os nomes do domínio."""
        raw = {
            "mean": self.mean, "mu": self.mu, "k": self.k, "cv": self.cv, "min": self.min_value,
            "mode": self.mode, "max": self.max_value, "loc": self.loc, "scale": self.scale,
        }
        return {name: value for name, value in raw.items() if value is not None}


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

class ServiceOut(BaseModel):
    distribution: str
    label: str
    mean: float = Field(description="Tempo médio de serviço E[S].")
    std: float = Field(description="Desvio padrão do serviço.")
    variance: float
    cv: float = Field(description="Coeficiente de variação (desvio / média).")
    mu: float = Field(description="Taxa de serviço equivalente, 1/E[S].")
    parameters: dict[str, float] = Field(description="Parâmetros efetivos, incluindo os derivados (ex.: forma do Weibull).")


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
