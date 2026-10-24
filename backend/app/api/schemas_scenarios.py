"""Esquemas da API de comparação de cenários (/api/scenarios, Fase 12)."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt

from app.api.schemas import ModelKey
from app.api.schemas_service import ServiceOut, ServiceSpec

_MODE = "absolute: o valor é o novo valor. relative: λ, μ e CV em % da base (20 = +20%); servers, capacity e k em unidades (1 = um a mais)."


# ---------- entrada ----------

class OverrideIn(BaseModel):
    mode: Literal["absolute", "relative"] = Field(description=_MODE)
    value: StrictFloat = Field(description="Valor absoluto, ou variação relativa à base.")


class ScenarioBaseIn(BaseModel):
    """A configuração do Laboratório (o mesmo que o /api/sizing recebe)."""

    model_config = ConfigDict(populate_by_name=True)

    model: ModelKey = Field(description="Modelo da base.")
    lam: StrictFloat = Field(alias="lambda", description="Taxa de chegada λ.")
    mu: StrictFloat | None = Field(default=None, description="Taxa de serviço μ. Obrigatória, exceto em mg1 e mgc (use `service`).")
    service: ServiceSpec | None = Field(default=None, description="Serviço do mg1 e do mgc.")
    servers: StrictInt | None = Field(default=None, description="c. Obrigatório em mmc, mmck, erlangb e mgc.")
    capacity: StrictInt | None = Field(default=None, description="K. Obrigatório em mm1k e mmck.")


class ScenarioIn(BaseModel):
    """Um cenário: a base com alguns valores trocados. O que não vier fica como na base."""

    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, description="Nome exibido (até 60 caracteres). Padrão: Cenário n.")
    model: ModelKey | None = Field(default=None, description="Troca o modelo. M/M/1, M/M/1/K e M/G/1 ficam com c = 1; no Erlang-B, K = c.")
    lam: OverrideIn | None = Field(default=None, alias="lambda", description="λ do cenário.")
    mu: OverrideIn | None = Field(default=None, description="μ do cenário. Nos modelos M/G reescala o serviço preservando o CV.")
    servers: OverrideIn | None = Field(default=None, description="c do cenário (modelos com mais de um servidor).")
    capacity: OverrideIn | None = Field(default=None, description="K do cenário (M/M/1/K e M/M/c/K).")
    cv: OverrideIn | None = Field(default=None, description="CV do serviço, mantendo a média (M/G com lognormal ou Weibull).")
    k: OverrideIn | None = Field(default=None, description="Etapas k do serviço Erlang-k, mantendo a média (M/G).")
    service: ServiceSpec | None = Field(default=None, description="Troca o serviço inteiro (só M/G/1 e M/G/c).")


class ScenariosRequest(BaseModel):
    model_config = ConfigDict(json_schema_extra={"examples": [{
        "base": {"model": "mmc", "lambda": 8, "mu": 1, "servers": 10},
        "scenarios": [
            {"name": "Pico (+20% de λ)", "lambda": {"mode": "relative", "value": 20}},
            {"name": "Mais um servidor", "servers": {"mode": "relative", "value": 1}},
        ],
        "simulation_time": 2000, "replications": 10, "warmup_time": 100, "seed": 2026,
    }]})

    base: ScenarioBaseIn
    scenarios: list[ScenarioIn] = Field(description="De 1 a 10 cenários, além da base.")
    simulation_time: StrictFloat = Field(description="Duração T de cada réplica (a mesma em todos os cenários).")
    replications: StrictInt = Field(default=10, description="Réplicas R por cenário (2 a 100), com as mesmas sementes.")
    warmup_time: StrictFloat = Field(default=0.0, description="Warm-up descartado no início de cada réplica.")
    seed: StrictInt | None = Field(default=None, description="Semente. Sem ela, uma é sorteada e devolvida (reproduz o resultado).")
    confidence_level: StrictFloat = Field(default=0.95, description="Nível dos intervalos de confiança.")
    bonferroni: StrictBool = Field(default=False, description="Corrige os ICs das diferenças pelo número de cenários (α/m).")


# ---------- saída (documenta o corpo do NDJSON e do resultado final) ----------

class ScenarioSummaryOut(BaseModel):
    mean: float
    std: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    n: int


class ScenarioMetricOut(BaseModel):
    analytic: float | None = Field(description="Valor analítico; None se o modelo não o tem ou o cenário é instável.")
    simulation: ScenarioSummaryOut | None = Field(description="Média e IC t entre as réplicas.")
    diff: ScenarioSummaryOut | None = Field(description="Diferença pareada contra a base (média e IC t sobre as d_i).")
    relative_change: float | None = Field(description="Diferença média / média simulada da base.")
    verdict: Literal["higher", "lower", "inconclusive"] | None = Field(
        description="higher/lower: o IC da diferença exclui 0. inconclusive: contém 0 (não significa igual).")
    analytic_diff: float | None
    analytic_relative_change: float | None
    analytic_diff_in_ci: bool | None = Field(description="Se a diferença analítica está dentro do IC pareado.")


class ScenarioChangeOut(BaseModel):
    field: str
    from_value: Any | None = None
    to_value: Any | None = None


class ScenarioAlertOut(BaseModel):
    code: Literal["unstable", "at_risk", "approximation"]
    level: Literal["error", "warning"]
    message: str


class ScenarioParametersOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    model: ModelKey
    lam: float = Field(alias="lambda")
    mu: float
    servers: int
    capacity: int | None = None
    service: ServiceOut | None = None


class ScenarioRowOut(BaseModel):
    index: int = Field(description="0 é a base; os cenários seguem a ordem do pedido (1, 2, ...).")
    role: Literal["base", "scenario"]
    name: str
    model: ModelKey
    model_label: str
    status: Literal["ok", "unstable", "error"] = Field(description="unstable: não simulado. error: amostra insuficiente.")
    message: str | None = None
    parameters: ScenarioParametersOut = Field(description="Valores já resolvidos.")
    changes: list[ScenarioChangeOut]
    alerts: list[ScenarioAlertOut]
    offered_utilization: float
    analytic_exact: bool
    metrics: dict[str, ScenarioMetricOut]


class ScenarioSettingsOut(BaseModel):
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    bonferroni: bool
    diff_confidence_level: float
    simulated_scenarios: int
    expected_arrivals: float


class ScenarioMultipleComparisonOut(BaseModel):
    correction: Literal["none", "bonferroni"]
    comparisons: int
    confidence_level: float
    individual_intervals: bool = Field(description="True quando há mais de um cenário e os ICs não foram corrigidos.")
    note: str


class ScenariosResultOut(BaseModel):
    settings: ScenarioSettingsOut
    multiple_comparison: ScenarioMultipleComparisonOut
    base: ScenarioRowOut
    scenarios: list[ScenarioRowOut]


class ScenarioEventOut(BaseModel):
    """Uma linha do NDJSON. start → base → scenario (um por cenário) → done; error encerra."""

    type: Literal["start", "base", "scenario", "done", "error"]
    total: int | None = Field(default=None, description="Simulações do pedido (base + cenários), em start, base e scenario.")
    completed: int | None = Field(default=None, description="Quantas já terminaram (para a barra de progresso).")
    settings: ScenarioSettingsOut | None = None
    multiple_comparison: ScenarioMultipleComparisonOut | None = None
    scenario: ScenarioRowOut | None = None
    result: ScenariosResultOut | None = Field(default=None, description="Resultado completo, só em done.")
    code: str | None = None
    message: str | None = None
    field: str | None = None
