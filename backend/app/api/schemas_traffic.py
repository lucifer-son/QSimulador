"""Esquemas da API do cruzamento semaforizado (/api/traffic, Fases 13.1 e 13.2).

Tempos em segundos, taxas em veículos por segundo. Os resultados são documentados de forma resumida
(`dict`); o formato completo está descrito em docs/como-executar.md e nos exemplos das rotas.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictFloat, StrictInt

from app.api.schemas_service import ServiceSpec


class PhaseIn(BaseModel):
    green: StrictFloat = Field(description="Verde da fase (s).")
    amber: StrictFloat = Field(default=0.0, description="Amarelo (s).")
    all_red: StrictFloat = Field(default=0.0, description="Todo-vermelho depois do amarelo (s).")


class PhasePatch(BaseModel):
    """O que trocar em uma fase do plano alternativo. O que não vier fica como na base."""

    green: StrictFloat | None = None
    amber: StrictFloat | None = None
    all_red: StrictFloat | None = None

    def values(self) -> dict[str, float]:
        return {k: v for k, v in (("green", self.green), ("amber", self.amber), ("all_red", self.all_red)) if v is not None}


class BlockIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    duration: StrictFloat = Field(description="Duração do bloco (s).")
    lam: StrictFloat | None = Field(default=None, alias="lambda", description="Taxa de chegada no bloco (veículos/s). Pode ser 0. Omitida quando o bloco traz `count`.")
    count: StrictInt | None = Field(
        default=None, description="Reproduz uma sessão: nº fixo de chegadas no bloco (só o instante é sorteado). Todos os blocos ou nenhum.")
    class_counts: dict[str, StrictInt] | None = Field(
        default=None, description="Com `count` e `classes`: chegadas de cada classe no bloco (nome → nº; a soma é `count`).")


class ClassIn(BaseModel):
    name: str = Field(description="Nome da classe (carro, moto, ônibus...).")
    share: StrictFloat = Field(description="Parcela da demanda (as parcelas somam 1).")
    factor: StrictFloat = Field(description="Equivalência em carros: quanto de linha de retenção o veículo ocupa em relação a um carro. Sem valor padrão.")


class ApproachIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    name: str | None = Field(default=None, description="Nome exibido (até 60 caracteres).")
    lam: StrictFloat | None = Field(default=None, alias="lambda", description="Taxa de chegada constante (veículos/s). Informe isto ou `profile`.")
    profile: list[BlockIn] | None = Field(default=None, description="Taxa de chegada por blocos consecutivos a partir de t = 0.")
    headway: ServiceSpec = Field(description="Intervalo entre veículos que cruzam a linha de retenção (s), medido no vídeo. Sem valor padrão.")
    first_vehicle_time: StrictFloat | None = Field(
        default=None, description="ℓ: segundos do início do verde até o 1º veículo da fila cruzar. Não informado → 0, com aviso.")
    first_vehicle_cv: StrictFloat | None = Field(
        default=None, description="CV de ℓ entre ciclos (a partida varia de um verde para outro). Não informado ou 0 → ℓ constante.")
    amber_usable: StrictFloat | None = Field(default=None, description="Segundos do amarelo em que ainda se cruza. Não informado → 0, com aviso.")
    initial_queue: StrictInt | None = Field(default=None, description="Veículos já esperando em t = 0. Não informado → 0, com aviso.")
    classes: list[ClassIn] | None = Field(
        default=None, description="Classes de veículos (até 8). `headway` passa a ser o intervalo de um carro; cada veículo ocupa h · fator da sua classe.")

    def spec(self) -> dict:
        return {
            "name": self.name, "lam": self.lam,
            "profile": None if self.profile is None else [
                {"duration": b.duration, "lam": b.lam, "count": b.count, "class_counts": b.class_counts} for b in self.profile],
            "classes": None if self.classes is None else [{"name": c.name, "share": c.share, "factor": c.factor} for c in self.classes],
            "headway": (self.headway.distribution, self.headway.service_values()),
            "first_vehicle_time": self.first_vehicle_time, "first_vehicle_cv": self.first_vehicle_cv, "amber_usable": self.amber_usable, "initial_queue": self.initial_queue,
        }


class CrossingIn(BaseModel):
    """O cruzamento: ciclo de 2 a 4 fases e uma aproximação por fase."""

    phases: list[PhaseIn] = Field(description="De 2 a 4 fases em sequência: a fase i atende a aproximação i.")
    offset: StrictFloat | None = Field(
        default=None, description="Segundos do ciclo já decorridos em t = 0 (0 = o verde da fase 1 começa em t = 0). Não informado → 0, com aviso.")
    approaches: list[ApproachIn] = Field(description="Uma aproximação por fase (2 a 4).")

    def spec(self) -> dict:
        return {"phases": [p.model_dump() for p in self.phases], "offset": self.offset, "approaches": [a.spec() for a in self.approaches]}


class RunIn(BaseModel):
    simulation_time: StrictFloat = Field(description="Duração simulada T (s). Máx. 86 400.")
    replications: StrictInt = Field(default=10, description="Réplicas independentes (2 a 100).")
    warmup_time: StrictFloat = Field(default=0.0, description="Aquecimento descartado (s). Use 0 para reproduzir uma gravação.")
    seed: StrictInt | None = Field(default=None, description="Semente (reprodutível). Sem semente, uma é sorteada e devolvida.")
    confidence_level: StrictFloat = Field(default=0.95, description="Nível dos ICs.")


class SimulateRequest(CrossingIn, RunIn):
    series_step: StrictFloat | None = Field(default=None, description="Passo da série temporal da fila (s). Padrão: ~240 pontos.")


class PlanIn(BaseModel):
    name: str | None = Field(default=None, description="Nome exibido (até 60 caracteres). Padrão: Plano n.")
    phases: list[PhasePatch | None] = Field(description="Um item por fase: o que trocar nela (null mantém a fase).")


class CompareRequest(CrossingIn, RunIn):
    scenarios: list[PlanIn] = Field(description="De 1 a 10 planos alternativos, além da referência.")
    bonferroni: StrictBool = Field(default=False, description="Corrige o nível dos ICs das diferenças pelo número de planos.")
    series_step: StrictFloat | None = None


class SweepRequest(CrossingIn, RunIn):
    min_green: list[StrictFloat] = Field(description="Verde mínimo das duas fases varridas (s), definido por quem conhece a segurança do cruzamento. Sem valor padrão.")
    pair: list[StrictInt] | None = Field(default=None, description="As duas fases (1 a 4) cujo verde é redistribuído. Padrão: 1 e 2.")
    step: StrictFloat = Field(description="Passo da varredura (s). Até 40 pontos.")


class TrafficResultOut(BaseModel):
    """Resultado da simulação: configuração, plano, aproximações, avisos, métricas com IC, referência analítica e série da fila."""

    settings: dict[str, Any]
    plan: dict[str, Any]
    approaches: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    metrics: dict[str, dict[str, Any]]
    reference: dict[str, Any]
    series: dict[str, Any] | None = None


class TrafficEventOut(BaseModel):
    """Uma linha do NDJSON: `type` é start, base, plan, point, done ou error; o resto depende do tipo."""

    model_config = ConfigDict(extra="allow")

    type: str
    total: int | None = None
    completed: int | None = None
    code: str | None = None
    message: str | None = None
    field: str | None = None


class VideoEstimateOut(BaseModel):
    """Estimativas a partir das planilhas do vídeo: plano, chegadas, descarga e o corpo sugerido para /simulate."""

    model_config = ConfigDict(extra="allow")

    session_id: str | None
    horizon: float
    approach_ids: list[str]
    method: dict[str, Any]
    signal: dict[str, Any]
    arrivals: dict[str, Any]
    discharge: dict[str, Any] | None
    suggested: dict[str, Any]
    notes: list[str]


class VideoValidationOut(BaseModel):
    """Simulado × observado por intervalo, com erros e cobertura da faixa simulada."""

    model_config = ConfigDict(extra="allow")

    approaches: dict[str, Any]
    settings: dict[str, Any]
    notes: list[str]


class SessionsCompareRequest(BaseModel):
    """Duas respostas de /video/estimate (por exemplo, manhã e tarde)."""

    a: dict[str, Any] = Field(description="Resposta de /video/estimate da primeira sessão.")
    b: dict[str, Any] = Field(description="Resposta de /video/estimate da segunda sessão.")
    label_a: str = Field(default="Sessão A", max_length=40)
    label_b: str = Field(default="Sessão B", max_length=40)
    confidence_level: StrictFloat = Field(default=0.95, description="Nível dos ICs da razão de taxas.")


class SessionsCompareOut(BaseModel):
    """Linhas de comparação (grupo, grandeza, valores, diferença, p-valor), as sessões e observações."""

    model_config = ConfigDict(extra="allow")

    labels: list[str]
    level: float
    rows: list[dict[str, Any]]
    notes: list[str]
    sessions: list[dict[str, Any]]
