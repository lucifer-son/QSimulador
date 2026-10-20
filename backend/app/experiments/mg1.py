"""Experimentos do serviço geral M/G/1 (varredura, sensibilidade e comparação de distribuições).

Nos modelos markovianos o serviço é só μ. No M/G/1 ele é uma distribuição, então, além de λ e μ,
dá para variar a *variabilidade* do serviço (o CV), que é o que a fórmula de Pollaczek-Khinchine
destaca. As variáveis do M/G/1:

- `lambda`: taxa de chegada;
- `mu`: taxa de serviço equivalente (1/E[S]); muda a escala do serviço e preserva a forma (o CV);
- `cv`: coeficiente de variação, mantendo E[S] (lognormal e Weibull);
- `k`: número de etapas (Erlang-k; CV = 1/√k), mantendo E[S].

Pontos instáveis (ρ ≥ 1) ou fora do domínio da distribuição são sinalizados e a faixa continua.
"""

import secrets
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace

from app.analytical.mg1 import mg1_metrics
from app.domain.service.distributions import (
    ERLANG, LOGNORMAL, TRIANGULAR, TRUNCATED_NORMAL, UNIFORM, WEIBULL,
    ServiceDistribution, build_distribution,
)
from app.domain.validation.errors import (
    InsufficientSampleError, QueueValidationError, UnstableSystemError,
)
from app.domain.validation.experiments import (
    MAX_COMPARED_SERVICES,
    validate_delta_pct,
    validate_range,
    validate_sweep_simulation,
)
from app.domain.validation.numbers import validate_positive_finite
from app.experiments.points import STATUS_INVALID, STATUS_OK, STATUS_UNSTABLE, PointEvaluation
from app.experiments.sensitivity import (
    ParameterSensitivity, SensitivityResult, SensitivitySide, _clean, _effects,
)
from app.experiments.sweep import SimulationSettings, SweepPoint, SweepResult
from app.simulation.mg1 import simulate_mg1

SHAPE_VARIABLE = {ERLANG: "k", LOGNORMAL: "cv", WEIBULL: "cv"}   # variável de forma de cada distribuição
_SCALED = {                                                       # parâmetros em unidade de tempo
    "deterministic": ("mean",), "exponential": ("mean",), ERLANG: ("mean",),
    LOGNORMAL: ("mean",), WEIBULL: ("mean",),
    UNIFORM: ("min", "max"), TRIANGULAR: ("min", "mode", "max"), TRUNCATED_NORMAL: ("loc", "scale"),
}

ServiceValues = Mapping[str, float | int]


def sweepable_variables_mg1(distribution: str) -> tuple[str, ...]:
    shape = SHAPE_VARIABLE.get(distribution)
    return ("lambda", "mu") + ((shape,) if shape else ())


def validate_mg1_variable(distribution: str, variable: object) -> str:
    allowed = sweepable_variables_mg1(distribution)
    if variable not in allowed:
        raise QueueValidationError(
            f"Para o M/G/1 com distribuição {distribution}, a variável varrida deve ser uma de: "
            f"{', '.join(allowed)}.",
            "variable",
        )
    return str(variable)


def _identity_values(distribution: str, values: ServiceValues) -> dict[str, float | int]:
    """Parâmetros com `mu` convertido em `mean`, para poder reescalar o serviço."""
    out = dict(values)
    if "mu" in out:
        mu = out.pop("mu")
        if "mean" in out:
            raise QueueValidationError("Informe a média (mean) ou a taxa de serviço (mu), não os dois.", "mean")
        if isinstance(mu, bool) or not isinstance(mu, (int, float)) or mu <= 0:
            raise QueueValidationError("mu deve ser maior que zero.", "mu")
        out["mean"] = 1.0 / mu
    return out


def _rescaled(distribution: str, values: ServiceValues, mean: float) -> ServiceDistribution:
    """Serviço com a mesma forma (mesmo CV) e a média `mean`."""
    base = build_distribution(distribution, values)
    factor = mean / base.mean
    scaled = {k: (v * factor if k in _SCALED[distribution] else v) for k, v in values.items()}
    return build_distribution(distribution, scaled)


def service_at(distribution: str, values: ServiceValues, variable: str, value: float) -> ServiceDistribution:
    """Serviço do ponto em que `variable` vale `value` (as demais variáveis ficam no valor base)."""
    values = _identity_values(distribution, values)
    if variable == "mu":
        return _rescaled(distribution, values, 1.0 / value)
    if variable == "cv":
        return build_distribution(distribution, {**values, "cv": value})
    if variable == "k":
        return build_distribution(distribution, {**values, "k": int(value)})
    return build_distribution(distribution, values)


def mg1_experiment_metrics(lam: float, service: ServiceDistribution) -> dict[str, float]:
    """As sete métricas do M/G/1 (a vazão é λ, como no M/M/1)."""
    return {**mg1_metrics(lam, service).as_dict(), "throughput": float(lam)}


def evaluate_mg1_point(lam: float, service: ServiceDistribution) -> PointEvaluation:
    try:
        return PointEvaluation(STATUS_OK, None, mg1_experiment_metrics(lam, service))
    except UnstableSystemError as error:
        return PointEvaluation(STATUS_UNSTABLE, str(error), None)
    except QueueValidationError as error:
        return PointEvaluation(STATUS_INVALID, str(error), None)


def _point_service(
    distribution: str, values: ServiceValues, variable: str, value: float
) -> tuple[ServiceDistribution | None, str | None]:
    try:
        return service_at(distribution, values, variable, value), None
    except QueueValidationError as error:
        return None, str(error)


def _require_lambda(lam: object) -> float:
    if lam is None:
        raise QueueValidationError("lambda é obrigatório (a menos que seja o parâmetro varrido).", "lambda")
    return validate_positive_finite("λ", lam)


def run_mg1_sweep(
    distribution: str,
    values: ServiceValues,
    variable: str,
    start: float,
    end: float,
    step: float,
    *,
    lam: float | None = None,
    simulation: SimulationSettings | None = None,
) -> SweepResult:
    """Varre `lambda`, `mu`, `cv` ou `k` de um M/G/1 e calcula as métricas de cada ponto.

    `values` são os parâmetros do serviço do ponto base (os da API: mean ou mu, cv, k...); eles
    precisam formar uma distribuição válida. Com `simulation`, cada ponto estável também é
    simulado, todos com a mesma semente (números aleatórios comuns).
    """
    variable = validate_mg1_variable(distribution, variable)
    grid = validate_range(variable, start, end, step)
    base_values = _identity_values(distribution, values)
    base = build_distribution(distribution, base_values)
    lam_fixed = None if variable == "lambda" else _require_lambda(lam)

    fixed: dict[str, float] = {}
    if variable != "lambda":
        fixed["lambda"] = lam_fixed
    if variable in ("lambda", "cv", "k"):
        fixed["mu"] = base.mu
    if variable in ("lambda", "mu"):
        fixed["cv"] = base.cv

    def lam_of(value: float) -> float:
        return float(value) if variable == "lambda" else lam_fixed

    services: list[ServiceDistribution | None] = []
    points: list[SweepPoint] = []
    for value in grid:
        service, error = _point_service(distribution, base_values, variable, float(value))
        services.append(service)
        if service is None:
            points.append(SweepPoint(float(value), STATUS_INVALID, error, 0.0, None, None))
            continue
        evaluation = evaluate_mg1_point(lam_of(value), service)
        points.append(SweepPoint(
            value=float(value), status=evaluation.status, message=evaluation.message,
            offered_utilization=lam_of(value) * service.mean,
            metrics=evaluation.metrics, simulation=None,
        ))

    used = None
    if simulation is not None:
        stable = [i for i, p in enumerate(points) if p.status == STATUS_OK]
        T, reps, warmup, seed, level = validate_sweep_simulation(
            [lam_of(grid[i]) for i in stable],
            simulation.simulation_time, simulation.replications, simulation.warmup_time,
            simulation.seed, simulation.confidence_level,
        )
        if seed is None:
            seed = secrets.randbits(32)
        used = SimulationSettings(T, reps, warmup, seed, level)
        for i in stable:
            try:
                summary = simulate_mg1(lam_of(grid[i]), services[i], T, reps, warmup, seed, level).summary
            except InsufficientSampleError as error:
                points[i] = replace(points[i], message=str(error))
            else:
                points[i] = replace(points[i], simulation=summary)

    return SweepResult(
        model="mg1", variable=variable, fixed=fixed, points=points, simulation=used,
        service=base.describe(),
    )


# ---------- sensibilidade ----------

def _mg1_side(distribution: str, values: ServiceValues, lam: float, name: str, value: float) -> SensitivitySide:
    if name == "k" and value < 1:
        return SensitivitySide(value, STATUS_INVALID, "k ficaria menor que 1.", None)
    lam_p = value if name == "lambda" else lam
    service, error = _point_service(distribution, values, name, value)
    if service is None:
        return SensitivitySide(value, STATUS_INVALID, error, None)
    evaluation = evaluate_mg1_point(lam_p, service)
    return SensitivitySide(value, evaluation.status, evaluation.message, evaluation.metrics)


def run_mg1_sensitivity(
    distribution: str, values: ServiceValues, lam: float, delta_pct: float = 10.0
) -> SensitivityResult:
    """Sensibilidade do M/G/1 a λ, μ e à variabilidade do serviço (CV, ou k no Erlang).

    O ponto base precisa ser estável (ρ < 1). λ, μ e CV variam ±delta_pct %; k varia ±1.
    """
    delta = validate_delta_pct(delta_pct)
    lam_v = validate_positive_finite("λ", lam)
    base_values = _identity_values(distribution, values)
    base_service = build_distribution(distribution, base_values)
    base_metrics = mg1_experiment_metrics(lam_v, base_service)   # levanta se ρ ≥ 1

    base: dict[str, float] = {"lambda": lam_v, "mu": base_service.mu}
    shape = SHAPE_VARIABLE.get(distribution)
    if shape == "cv":
        base["cv"] = base_service.cv
    elif shape == "k":
        base["k"] = float(base_values["k"])

    factor = delta / 100
    perturbations: list[tuple[str, str, float, float]] = [
        ("lambda", "percent", _clean(lam_v * (1 - factor)), _clean(lam_v * (1 + factor))),
        ("mu", "percent", _clean(base["mu"] * (1 - factor)), _clean(base["mu"] * (1 + factor))),
    ]
    if shape == "cv":
        perturbations.append(("cv", "percent", _clean(base["cv"] * (1 - factor)), _clean(base["cv"] * (1 + factor))))
    elif shape == "k":
        perturbations.append(("k", "units", base["k"] - 1, base["k"] + 1))

    parameters = []
    for name, kind, low_value, high_value in perturbations:
        low = _mg1_side(distribution, base_values, lam_v, name, low_value)
        high = _mg1_side(distribution, base_values, lam_v, name, high_value)
        parameters.append(ParameterSensitivity(
            name=name, base_value=base[name], perturbation=kind, low=low, high=high,
            effects=_effects(base_metrics, base[name], low, high),
        ))
    return SensitivityResult(
        model="mg1", delta_pct=delta, base=base, base_metrics=base_metrics, parameters=parameters,
        service=base_service.describe(),
    )


# ---------- comparação de distribuições ----------

@dataclass(frozen=True)
class ServiceSeries:
    service: dict                      # descrição da distribuição (média, CV, parâmetros)
    points: list[SweepPoint]


@dataclass(frozen=True)
class ServicesComparisonResult:
    model: str
    series: list[ServiceSeries]

    def as_dict(self) -> dict:
        return asdict(self)


def validate_service_list(specs: object) -> list[tuple[str, dict]]:
    if not isinstance(specs, (list, tuple)) or not 2 <= len(specs) <= MAX_COMPARED_SERVICES:
        raise QueueValidationError(
            f"services deve ter de 2 a {MAX_COMPARED_SERVICES} distribuições.", "services"
        )
    return list(specs)


def run_services_comparison(
    services: list[tuple[str, dict]], start: float, end: float, step: float
) -> ServicesComparisonResult:
    """Compara distribuições de serviço, variando λ na mesma faixa para todas.

    Cada item é (distribuição, parâmetros). Uma distribuição que satura antes das outras só tem
    pontos instáveis a partir do seu ρ = 1; as demais séries continuam.
    """
    specs = validate_service_list(services)
    built = [build_distribution(key, _identity_values(key, values)) for key, values in specs]
    series = []
    for service in built:
        result = run_mg1_sweep(service.key, _canonical(service), "lambda", start, end, step)
        series.append(ServiceSeries(service.describe(), result.points))
    return ServicesComparisonResult(model="mg1", series=series)


def _canonical(service: ServiceDistribution) -> dict[str, float | int]:
    """Parâmetros de entrada que reconstroem `service` (os efetivos, sem os derivados)."""
    p = service.parameters
    if service.key in ("deterministic", "exponential"):
        return {"mean": service.mean}
    if service.key == ERLANG:
        return {"mean": service.mean, "k": int(p["k"])}
    if service.key in (LOGNORMAL, WEIBULL):
        return {"mean": service.mean, "cv": p["cv"]}
    if service.key == UNIFORM:
        return {"min": p["min"], "max": p["max"]}
    if service.key == TRIANGULAR:
        return {"min": p["min"], "mode": p["mode"], "max": p["max"]}
    return {"loc": p["loc"], "scale": p["scale"]}
