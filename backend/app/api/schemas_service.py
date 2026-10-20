"""Esquemas do serviço geral compartilhados pelo M/G/1 e pelos experimentos (Fases 9 e 10)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictFloat, StrictInt

DistributionKey = Literal[
    "deterministic", "exponential", "erlang", "lognormal", "weibull",
    "uniform", "triangular", "truncated_normal",
]

_UNUSED = " Ignorado pelas distribuições que não usam este parâmetro."



class ServiceSpec(BaseModel):
    """Distribuição do tempo de serviço e seus parâmetros (usada pelo M/G/1 e pelos experimentos)."""

    model_config = ConfigDict(populate_by_name=True)

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


class ServiceOut(BaseModel):
    distribution: str
    label: str
    mean: float = Field(description="Tempo médio de serviço E[S].")
    std: float = Field(description="Desvio padrão do serviço.")
    variance: float
    cv: float = Field(description="Coeficiente de variação (desvio / média).")
    mu: float = Field(description="Taxa de serviço equivalente, 1/E[S].")
    parameters: dict[str, float] = Field(description="Parâmetros efetivos, incluindo os derivados (ex.: forma do Weibull).")
