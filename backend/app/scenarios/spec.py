"""Cenários: a base (configuração do Laboratório) e as sobrescritas aplicadas sobre ela.

Cada cenário é a base com alguns valores trocados. Um valor pode ser absoluto ("λ = 12") ou
relativo à base ("+20%" em λ, μ e CV; "+1 servidor" em c, K e k). `resolve_scenario` devolve o
cenário já com todos os valores resolvidos, que é o que a simulação e o analítico usam.

Regras de resolução (valem para o cenário, nunca alteram a base):
- `model` troca o modelo. Modelos de um servidor (M/M/1, M/M/1/K, M/G/1) ficam com c = 1; no
  Erlang-B a capacidade é K = c; M/M/1/K e M/M/c/K exigem K (herdado da base ou informado).
- Modelos markovianos têm serviço exponencial: ao trocar de M/G para um deles, o serviço vira
  exponencial com a mesma média. `service` (distribuição completa) só vale em M/G/1 e M/G/c.
- `mu` reescala o serviço preservando a forma (o CV); `cv` e `k` mudam a variabilidade mantendo
  a média, e só existem nas distribuições que os usam (lognormal e Weibull: cv; Erlang: k).
- Ordem de aplicação: modelo, serviço, μ, CV, k.
"""

import math
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field

from app.domain.service.distributions import (
    ERLANG, ServiceDistribution, build_distribution,
)
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.experiments import (
    GENERAL_SERVICE_MODELS, MODELS, USES_CAPACITY, USES_SERVERS,
)
from app.domain.validation.mmck import validate_capacity, validate_servers
from app.domain.validation.numbers import validate_positive_finite
from app.experiments.general import (
    SHAPE_VARIABLE, _canonical, _identity_values, service_at,
)

MAX_SCENARIOS = 10                 # além da base (RNC-04)
MAX_NAME_LENGTH = 60
INFINITE_QUEUE_MODELS = ("mm1", "mmc", "mg1", "mgc")   # sem capacidade: podem ser instáveis

LABELS = {
    "mm1": "M/M/1", "mmc": "M/M/c", "mm1k": "M/M/1/K", "mmck": "M/M/c/K",
    "mg1": "M/G/1", "erlangb": "Erlang-B", "mgc": "M/G/c",
}

ABSOLUTE, RELATIVE = "absolute", "relative"
MODES = (ABSOLUTE, RELATIVE)

ServiceInput = tuple[str, dict]   # (chave da distribuição, parâmetros no formato da API)


@dataclass(frozen=True)
class Override:
    """Novo valor de um parâmetro: absoluto, ou relativo à base (% em reais; unidades em inteiros)."""

    mode: str
    value: float


@dataclass(frozen=True)
class BaseSpec:
    """A configuração do Laboratório, no formato da API."""

    model: str
    lam: float
    mu: float | None = None
    servers: int | None = None
    capacity: int | None = None
    service: ServiceInput | None = None


@dataclass(frozen=True)
class ScenarioSpec:
    """Sobrescritas de um cenário; o que não vier fica como na base."""

    name: str | None = None
    model: str | None = None
    lam: Override | None = None
    mu: Override | None = None
    servers: Override | None = None
    capacity: Override | None = None
    cv: Override | None = None
    k: Override | None = None
    service: ServiceInput | None = None


@dataclass(frozen=True)
class Resolved:
    """Cenário com todos os valores resolvidos: o que a simulação e o analítico recebem."""

    name: str
    model: str
    lam: float
    servers: int
    capacity: int | None            # K; None nas filas ilimitadas (e no Erlang-B, onde K = c)
    service: ServiceDistribution = field(compare=False)

    @property
    def sim_capacity(self) -> int | None:
        """Capacidade que a simulação usa: no Erlang-B, K = c."""
        return self.servers if self.model == "erlangb" else self.capacity

    @property
    def offered_utilization(self) -> float:
        return self.lam * self.service.mean / self.servers

    @property
    def general_service(self) -> bool:
        return self.model in GENERAL_SERVICE_MODELS

    @property
    def label(self) -> str:
        return LABELS[self.model]

    def parameters(self) -> dict:
        """Valores resolvidos, como a resposta os devolve (sem o ruído de ponto flutuante)."""
        return {
            "model": self.model,
            "lambda": _clean(self.lam),
            "mu": _clean(self.service.mu),
            "servers": self.servers,
            "capacity": self.capacity,
            "service": self.service.describe() if self.general_service else None,
        }


def _clean(value: float) -> float:
    """Remove o ruído de 1/(1/x): 0,3 não vira 0,30000000000000004 na resposta."""
    return float(f"{value:.12g}")


@contextmanager
def _under(prefix: str) -> Iterator[None]:
    """Prefixa o campo dos erros de domínio com o caminho no corpo (ex.: scenarios[2].cv)."""
    try:
        yield
    except QueueValidationError as error:
        field_name = f"{prefix}.{error.field}" if error.field else prefix
        raise type(error)(str(error), field_name) from None


def _fail(prefix: str, name: str, message: str) -> QueueValidationError:
    return QueueValidationError(message, f"{prefix}.{name}")


def _validate_model(model: object, prefix: str) -> str:
    if model not in MODELS:
        raise _fail(prefix, "model", f"model deve ser um de: {', '.join(MODELS)}.")
    return str(model)


# ---------- a base ----------

def resolve_base(spec: BaseSpec) -> Resolved:
    """Valida a base e a resolve (nome "Base"). Os campos dos erros começam com `base.`."""
    prefix = "base"
    model = _validate_model(spec.model, prefix)
    with _under(prefix):
        lam = validate_positive_finite("λ", spec.lam)
        if model in GENERAL_SERVICE_MODELS:
            if spec.service is None:
                raise QueueValidationError(f"service é obrigatório para o modelo {LABELS[model]}.", "service")
            key, values = spec.service
            service = build_distribution(key, _identity_values(key, values))
        else:
            if spec.mu is None:
                raise QueueValidationError(f"mu é obrigatório para o modelo {LABELS[model]}.", "mu")
            mu = validate_positive_finite("μ", spec.mu)
            service = build_distribution("exponential", {"mean": 1.0 / mu})

        servers = 1
        if USES_SERVERS[model]:
            if spec.servers is None:
                raise QueueValidationError(f"servers é obrigatório para o modelo {LABELS[model]}.", "servers")
            servers = validate_servers(spec.servers)
        capacity = None
        if USES_CAPACITY[model]:
            if spec.capacity is None:
                raise QueueValidationError(f"capacity é obrigatório para o modelo {LABELS[model]}.", "capacity")
            capacity = validate_capacity(spec.capacity, servers)
    return Resolved("Base", model, lam, servers, capacity, service)


# ---------- os cenários ----------

def _number(override: Override, name: str) -> float:
    if override.mode not in MODES:
        raise QueueValidationError(f"{name}: mode deve ser um de: {', '.join(MODES)}.", name)
    if isinstance(override.value, bool) or not isinstance(override.value, (int, float)) \
            or not math.isfinite(override.value):
        raise QueueValidationError(f"{name}: value deve ser um número finito.", name)
    return float(override.value)


def _real_value(override: Override | None, current: float, name: str) -> float:
    """Valor de λ, μ ou CV: absoluto, ou relativo em % (+20 → ×1,2). Erros sem prefixo (`_under` prefixa)."""
    if override is None:
        return current
    value = _number(override, name)
    if override.mode == RELATIVE:
        if value <= -100:
            raise QueueValidationError(f"{name}: a variação relativa deve ser maior que −100%.", name)
        value = current * (1 + value / 100)
    return value


def _int_value(override: Override | None, current: int | None, name: str) -> int | None:
    """Valor de c, K ou k: absoluto, ou relativo em unidades (+1 → um a mais)."""
    if override is None:
        return current
    value = _number(override, name)
    if value != int(value):
        raise QueueValidationError(f"{name} deve ser um número inteiro.", name)
    if override.mode == RELATIVE:
        if current is None:
            raise QueueValidationError(f"{name}: não há valor na base para aplicar a variação relativa.", name)
        return current + int(value)
    return int(value)


def resolve_scenario(base: Resolved, spec: ScenarioSpec, index: int) -> Resolved:
    """Aplica as sobrescritas à base. `index` (de 0) só serve para identificar o campo nos erros."""
    prefix = f"scenarios[{index}]"
    name = (spec.name or "").strip() or f"Cenário {index + 1}"
    if len(name) > MAX_NAME_LENGTH:
        raise _fail(prefix, "name", f"name deve ter no máximo {MAX_NAME_LENGTH} caracteres.")
    model = _validate_model(spec.model if spec.model is not None else base.model, prefix)
    general = model in GENERAL_SERVICE_MODELS
    label = LABELS[model]

    with _under(prefix):
        service = _resolve_service(base.service, spec, model, general, label)
        lam = validate_positive_finite("λ", _real_value(spec.lam, base.lam, "lambda"))

        servers = base.servers if USES_SERVERS[model] or spec.servers is not None else 1
        if spec.servers is not None:
            if not USES_SERVERS[model]:
                raise QueueValidationError(f"O modelo {label} tem um único servidor; retire servers.", "servers")
            servers = _int_value(spec.servers, base.servers, "servers")
        servers = validate_servers(servers)

        capacity = None
        if USES_CAPACITY[model]:
            capacity = base.capacity
            if spec.capacity is not None:
                capacity = _int_value(spec.capacity, base.capacity, "capacity")
            if capacity is None:
                raise QueueValidationError(
                    f"capacity é obrigatório para o modelo {label} (a base não tem capacidade).", "capacity")
            capacity = validate_capacity(capacity, servers)
        elif spec.capacity is not None:
            raise QueueValidationError(f"O modelo {label} não tem capacity (retire o campo).", "capacity")
    return Resolved(name, model, lam, servers, capacity, service)


def _resolve_service(
    base_service: ServiceDistribution, spec: ScenarioSpec, model: str, general: bool, label: str,
) -> ServiceDistribution:
    """Serviço do cenário: parte do da base e aplica modelo, serviço, μ, CV e k (nessa ordem)."""
    service = base_service
    if not general and service.key != "exponential":
        service = build_distribution("exponential", {"mean": service.mean})   # mesma média
    if spec.service is not None:
        if not general:
            raise QueueValidationError(f"service só se aplica aos modelos M/G/1 e M/G/c, não ao {label}.", "service")
        key, values = spec.service
        service = build_distribution(key, _identity_values(key, values))

    if spec.mu is not None:
        mu = _real_value(spec.mu, service.mu, "mu")
        mu = validate_positive_finite("μ", mu)
        service = service_at(service.key, _canonical(service), "mu", mu)
    if spec.cv is not None:
        _require_shape(service, "cv", label, general)
        cv = _real_value(spec.cv, service.cv, "cv")
        service = service_at(service.key, _canonical(service), "cv", cv)
    if spec.k is not None:
        _require_shape(service, "k", label, general)
        current_k = int(service.parameters["k"])
        k = _int_value(spec.k, current_k, "k")
        service = service_at(service.key, _canonical(service), "k", k)
    return service


def _require_shape(service: ServiceDistribution, variable: str, label: str, general: bool) -> None:
    """cv e k só existem nas distribuições que os usam (e, portanto, só nos modelos de serviço geral)."""
    if SHAPE_VARIABLE.get(service.key) == variable:
        return
    if not general:
        raise QueueValidationError(
            f"{variable} só se aplica aos modelos M/G/1 e M/G/c (o {label} tem serviço exponencial).", variable)
    if variable == "cv":
        raise QueueValidationError(
            f"cv só se aplica às distribuições lognormal e Weibull (o serviço do cenário é {service.label}).", "cv")
    raise QueueValidationError(
        f"k só se aplica à distribuição Erlang-k (o serviço do cenário é {service.label}).", "k")


def changes(base: Resolved, scenario: Resolved) -> list[dict]:
    """O que mudou em relação à base (valores já resolvidos), na ordem model, λ, μ, c, K, serviço, CV, k."""
    b, s = base.parameters(), scenario.parameters()
    out: list[dict] = []

    def add(name: str, before: object, after: object) -> None:
        if before != after:
            out.append({"field": name, "from_value": before, "to_value": after})

    add("model", b["model"], s["model"])
    add("lambda", b["lambda"], s["lambda"])
    add("mu", b["mu"], s["mu"])
    add("servers", b["servers"], s["servers"])
    add("capacity", b["capacity"], s["capacity"])
    if base.general_service or scenario.general_service:
        add("distribution", base.service.key if base.general_service else None,
            scenario.service.key if scenario.general_service else None)
        add("cv", _clean(base.service.cv) if base.general_service else None,
            _clean(scenario.service.cv) if scenario.general_service else None)
        if scenario.service.key == ERLANG or base.service.key == ERLANG:
            add("k", int(base.service.parameters["k"]) if base.service.key == ERLANG else None,
                int(scenario.service.parameters["k"]) if scenario.service.key == ERLANG else None)
    return out
