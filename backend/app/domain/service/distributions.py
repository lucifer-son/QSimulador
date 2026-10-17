"""Distribuições do tempo de serviço (Fase 9: M/D/1 e M/G/1).

Cada distribuição informa média, variância e CV e sabe gerar amostras. A média e a
variância vêm sempre da distribuição efetiva (no caso da normal truncada em zero, da
distribuição truncada, e não dos parâmetros originais), de modo que o analítico e a
simulação usam exatamente o mesmo serviço.

Parametrização (unidade de tempo, ex.: segundos):
- determinística, exponencial: média (`mean`) ou taxa (`mu`);
- Erlang-k: média + `k` (inteiro ≥ 1);
- lognormal e Weibull: média + `cv`;
- uniforme (`min`, `max`), triangular (`min`, `mode`, `max`) e normal truncada em zero
  (`loc`, `scale`): parâmetros próprios; a média e μ são calculados.
"""

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from numbers import Integral, Real

import numpy as np
from scipy import optimize, special, stats

from app.domain.validation.errors import QueueValidationError

DETERMINISTIC = "deterministic"
EXPONENTIAL = "exponential"
ERLANG = "erlang"
LOGNORMAL = "lognormal"
WEIBULL = "weibull"
UNIFORM = "uniform"
TRIANGULAR = "triangular"
TRUNCATED_NORMAL = "truncated_normal"

DISTRIBUTION_KEYS = (
    DETERMINISTIC, EXPONENTIAL, ERLANG, LOGNORMAL, WEIBULL, UNIFORM, TRIANGULAR, TRUNCATED_NORMAL,
)

MAX_ERLANG_K = 1000
MIN_CV, MAX_CV = 0.01, 10.0
MIN_STANDARDIZED_LOC = -10.0   # loc/scale mínimo da normal truncada (evita cauda numericamente degenerada)
_BLOCK = 2048                  # amostras geradas por vez (vetorizado) pelo amostrador

Draw = Callable[[np.random.Generator, int], np.ndarray]


@dataclass(frozen=True)
class ServiceDistribution:
    """Distribuição de serviço já parametrizada."""

    key: str
    label: str
    mean: float
    variance: float
    parameters: dict[str, float]    # parâmetros efetivos (inclui os derivados, ex.: forma do Weibull)
    _draw: Draw = field(repr=False, compare=False)

    @property
    def std(self) -> float:
        return math.sqrt(self.variance)

    @property
    def cv(self) -> float:
        return self.std / self.mean

    @property
    def mu(self) -> float:
        return 1.0 / self.mean

    def sample(self, rng: np.random.Generator, size: int) -> np.ndarray:
        return self._draw(rng, size)

    def sampler(self, rng: np.random.Generator) -> Callable[[], float]:
        """Função sem argumentos que devolve um tempo de serviço por chamada (gera em blocos)."""
        state = {"buf": np.empty(0), "i": 0}

        def next_value() -> float:
            if state["i"] >= len(state["buf"]):
                state["buf"] = self._draw(rng, _BLOCK)
                state["i"] = 0
            value = float(state["buf"][state["i"]])
            state["i"] += 1
            return value

        return next_value

    def describe(self) -> dict:
        return {
            "distribution": self.key, "label": self.label, "mean": self.mean, "std": self.std,
            "variance": self.variance, "cv": self.cv, "mu": self.mu, "parameters": dict(self.parameters),
        }


# ---------- catálogo (GET /api/distributions) ----------

@dataclass(frozen=True)
class ParameterSpec:
    name: str           # nome do campo na API
    label: str
    kind: str           # "float" | "int"
    description: str


@dataclass(frozen=True)
class DistributionSpec:
    key: str
    label: str
    description: str
    accepts_mean: bool   # aceita `mean` ou `mu` (média ou taxa de serviço)
    parameters: tuple[ParameterSpec, ...]   # além de mean/mu
    example: dict[str, float]


CATALOG: tuple[DistributionSpec, ...] = (
    DistributionSpec(DETERMINISTIC, "Determinística (M/D/1)", "Tempo de serviço constante (CV = 0).",
                     True, (), {"mean": 0.0125}),
    DistributionSpec(EXPONENTIAL, "Exponencial", "Serviço markoviano (CV = 1); reproduz o M/M/1.",
                     True, (), {"mean": 0.02}),
    DistributionSpec(ERLANG, "Erlang-k", "Soma de k etapas exponenciais iguais (CV = 1/√k).",
                     True, (ParameterSpec("k", "Etapas k", "int", "Inteiro maior ou igual a 1."),),
                     {"mean": 0.02, "k": 4}),
    DistributionSpec(LOGNORMAL, "Lognormal", "Cauda longa; a variabilidade é dada pelo CV.",
                     True, (ParameterSpec("cv", "CV", "float", "Coeficiente de variação (0,01 a 10)."),),
                     {"mean": 0.02, "cv": 1.5}),
    DistributionSpec(WEIBULL, "Weibull", "A forma é calculada a partir do CV informado.",
                     True, (ParameterSpec("cv", "CV", "float", "Coeficiente de variação (0,01 a 10)."),),
                     {"mean": 0.02, "cv": 0.8}),
    DistributionSpec(UNIFORM, "Uniforme", "Igualmente provável entre o mínimo e o máximo.",
                     False, (ParameterSpec("min", "Mínimo", "float", "Maior ou igual a 0."),
                             ParameterSpec("max", "Máximo", "float", "Maior que o mínimo.")),
                     {"min": 0.01, "max": 0.03}),
    DistributionSpec(TRIANGULAR, "Triangular", "Mínimo, valor mais provável (moda) e máximo.",
                     False, (ParameterSpec("min", "Mínimo", "float", "Maior ou igual a 0."),
                             ParameterSpec("mode", "Moda", "float", "Entre o mínimo e o máximo."),
                             ParameterSpec("max", "Máximo", "float", "Maior que o mínimo.")),
                     {"min": 0.01, "mode": 0.015, "max": 0.04}),
    DistributionSpec(TRUNCATED_NORMAL, "Normal truncada em 0",
                     "Normal(loc, scale) descartando valores negativos; média e variância são as da truncada.",
                     False, (ParameterSpec("loc", "Média da normal (loc)", "float", "Posição da normal original."),
                             ParameterSpec("scale", "Desvio da normal (scale)", "float", "Maior que zero.")),
                     {"loc": 0.02, "scale": 0.008}),
)
_SPEC = {spec.key: spec for spec in CATALOG}


# ---------- leitura e validação de parâmetros ----------

def _real(values: Mapping[str, object], name: str) -> float | None:
    value = values.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, Real):
        raise QueueValidationError(f"{name} deve ser um número real.", name)
    value = float(value)
    if not math.isfinite(value):
        raise QueueValidationError(f"{name} deve ser um número finito.", name)
    return value


def _required(values: Mapping[str, object], name: str) -> float:
    value = _real(values, name)
    if value is None:
        raise QueueValidationError(f"Informe {name}.", name)
    return value


def _positive(values: Mapping[str, object], name: str) -> float:
    value = _required(values, name)
    if value <= 0:
        raise QueueValidationError(f"{name} deve ser maior que zero.", name)
    return value


def _nonnegative(values: Mapping[str, object], name: str) -> float:
    value = _required(values, name)
    if value < 0:
        raise QueueValidationError(f"{name} não pode ser negativo.", name)
    return value


def _mean_from(values: Mapping[str, object]) -> float:
    mean, mu = _real(values, "mean"), _real(values, "mu")
    if mean is not None and mu is not None:
        raise QueueValidationError("Informe a média (mean) ou a taxa de serviço (mu), não os dois.", "mean")
    if mean is None and mu is None:
        raise QueueValidationError("Informe a média do serviço (mean) ou a taxa de serviço (mu).", "mean")
    if mean is not None:
        if mean <= 0:
            raise QueueValidationError("mean deve ser maior que zero.", "mean")
        return mean
    if mu <= 0:
        raise QueueValidationError("mu deve ser maior que zero.", "mu")
    return 1.0 / mu


def _cv(values: Mapping[str, object]) -> float:
    cv = _positive(values, "cv")
    if not MIN_CV <= cv <= MAX_CV:
        raise QueueValidationError(
            f"cv deve estar entre {MIN_CV:g} e {MAX_CV:g} (para CV = 0, use a distribuição determinística).", "cv")
    return cv


def _weibull_cv(shape: float) -> float:
    return math.sqrt(math.exp(special.gammaln(1 + 2 / shape) - 2 * special.gammaln(1 + 1 / shape)) - 1)


def _weibull_shape(cv: float) -> float:
    """Forma k tal que o CV da Weibull(k) é `cv` (o CV decresce com k)."""
    return float(optimize.brentq(lambda k: _weibull_cv(k) - cv, 0.1, 1000.0, xtol=1e-12))


def build_distribution(key: str, values: Mapping[str, object]) -> ServiceDistribution:
    """Valida os parâmetros e monta a distribuição. Levanta QueueValidationError com o campo."""
    if key not in _SPEC:
        raise QueueValidationError(f"Distribuição desconhecida: {key}.", "distribution")
    label = _SPEC[key].label

    if key == DETERMINISTIC:
        m = _mean_from(values)
        return ServiceDistribution(key, label, m, 0.0, {"mean": m}, lambda rng, n: np.full(n, m))

    if key == EXPONENTIAL:
        m = _mean_from(values)
        return ServiceDistribution(key, label, m, m * m, {"mean": m}, lambda rng, n: rng.exponential(m, n))

    if key == ERLANG:
        m = _mean_from(values)
        k = values.get("k")
        if k is None:
            raise QueueValidationError("Informe k.", "k")
        if isinstance(k, bool) or not isinstance(k, Integral):
            raise QueueValidationError("k deve ser um número inteiro.", "k")
        if not 1 <= k <= MAX_ERLANG_K:
            raise QueueValidationError(f"k deve estar entre 1 e {MAX_ERLANG_K}.", "k")
        k = int(k)
        return ServiceDistribution(key, label, m, m * m / k, {"mean": m, "k": float(k)},
                                   lambda rng, n: rng.gamma(k, m / k, n))

    if key == LOGNORMAL:
        m, cv = _mean_from(values), _cv(values)
        sigma2 = math.log1p(cv * cv)
        sigma, mu_ln = math.sqrt(sigma2), math.log(m) - sigma2 / 2
        return ServiceDistribution(key, label, m, (cv * m) ** 2, {"mean": m, "cv": cv, "sigma": sigma, "mu_log": mu_ln},
                                   lambda rng, n: rng.lognormal(mu_ln, sigma, n))

    if key == WEIBULL:
        m, cv = _mean_from(values), _cv(values)
        shape = _weibull_shape(cv)
        scale = m / math.exp(special.gammaln(1 + 1 / shape))
        return ServiceDistribution(key, label, m, (cv * m) ** 2, {"mean": m, "cv": cv, "shape": shape, "scale": scale},
                                   lambda rng, n: scale * rng.weibull(shape, n))

    if key == UNIFORM:
        a, b = _nonnegative(values, "min"), _positive(values, "max")
        if a >= b:
            raise QueueValidationError("max deve ser maior que min.", "max")
        return ServiceDistribution(key, label, (a + b) / 2, (b - a) ** 2 / 12, {"min": a, "max": b},
                                   lambda rng, n: rng.uniform(a, b, n))

    if key == TRIANGULAR:
        a, c, b = _nonnegative(values, "min"), _nonnegative(values, "mode"), _positive(values, "max")
        if a >= b:
            raise QueueValidationError("max deve ser maior que min.", "max")
        if not a <= c <= b:
            raise QueueValidationError("mode deve estar entre min e max (min ≤ moda ≤ max).", "mode")
        mean = (a + b + c) / 3
        var = (a * a + b * b + c * c - a * b - a * c - b * c) / 18
        return ServiceDistribution(key, label, mean, var, {"min": a, "mode": c, "max": b},
                                   lambda rng, n: rng.triangular(a, c, b, n))

    # TRUNCATED_NORMAL
    loc, scale = _required(values, "loc"), _positive(values, "scale")
    if loc / scale < MIN_STANDARDIZED_LOC:
        raise QueueValidationError(
            f"loc é negativo demais em relação a scale (loc/scale deve ser ≥ {MIN_STANDARDIZED_LOC:g}).", "loc")
    a = -loc / scale     # limite inferior padronizado (truncagem em 0)
    mean, var = (float(x) for x in stats.truncnorm.stats(a, np.inf, loc=loc, scale=scale, moments="mv"))
    if not (math.isfinite(mean) and math.isfinite(var) and mean > 0 and var >= 0):
        raise QueueValidationError("Parâmetros inválidos para a normal truncada.", "loc")
    return ServiceDistribution(
        key, label, mean, var, {"loc": loc, "scale": scale, "mean": mean},
        lambda rng, n: stats.truncnorm.rvs(a, np.inf, loc=loc, scale=scale, size=n, random_state=rng),
    )
