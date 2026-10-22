"""Experimentos dos modelos de serviço geral: M/G/1 e M/G/c (Fases 10 e 11).

Nos modelos markovianos o serviço é só μ. Nos modelos de serviço geral ele é uma distribuição,
então, além de λ e μ, dá para variar a *variabilidade* do serviço (o CV). As variáveis:

- `lambda`: taxa de chegada;
- `mu`: taxa de serviço equivalente (1/E[S]); muda a escala do serviço e preserva a forma (o CV);
- `servers`: número de servidores (só no M/G/c; o M/G/1 tem um servidor);
- `cv`: coeficiente de variação, mantendo E[S] (lognormal e Weibull);
- `k`: número de etapas (Erlang-k; CV = 1/√k), mantendo E[S].

O M/G/1 usa Pollaczek-Khinchine (exato) e o M/G/c, a aproximação de Allen–Cunneen. Com c = 1 os
dois coincidem, e é por isso que a mesma lógica serve aos dois. Pontos instáveis (ρ ≥ 1) ou fora
do domínio da distribuição são sinalizados e a faixa continua.
"""

import secrets
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace

from app.analytical.mg1 import mg1_metrics
from app.analytical.mgc import mgc_metrics
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
from app.domain.validation.mmck import validate_servers
from app.domain.validation.numbers import validate_positive_finite
from app.experiments.points import STATUS_INVALID, STATUS_OK, STATUS_UNSTABLE, PointEvaluation
from app.experiments.sensitivity import (
    ParameterSensitivity, SensitivityResult, SensitivitySide, _clean, _effects,
)
from app.experiments.sweep import (
    ServerComparisonResult, ServerSeries, SimulationSettings, SweepPoint, SweepResult,
)
from app.simulation.mg1 import simulate_mg1
from app.simulation.mgc import simulate_mgc

GENERAL_MODELS = ("mg1", "mgc")

SHAPE_VARIABLE = {ERLANG: "k", LOGNORMAL: "cv", WEIBULL: "cv"}   # variável de forma de cada distribuição
_SCALED = {                                                       # parâmetros em unidade de tempo
    "deterministic": ("mean",), "exponential": ("mean",), ERLANG: ("mean",),
    LOGNORMAL: ("mean",), WEIBULL: ("mean",),
    UNIFORM: ("min", "max"), TRIANGULAR: ("min", "mode", "max"), TRUNCATED_NORMAL: ("loc", "scale"),
}

ServiceValues = Mapping[str, float | int]


def _label(model: str) -> str:
    return "M/G/c" if model == "mgc" else "M/G/1"


def sweepable_variables_general(distribution: str, model: str = "mg1") -> tuple[str, ...]:
    """Variáveis varríveis: λ e μ, c (só no M/G/c) e a de forma da distribuição, se houver."""
    shape = SHAPE_VARIABLE.get(distribution)
    return ("lambda", "mu") + (("servers",) if model == "mgc" else ()) + ((shape,) if shape else ())


def sweepable_variables_mg1(distribution: str) -> tuple[str, ...]:
    return sweepable_variables_general(distribution, "mg1")


def validate_general_variable(distribution: str, variable: object, model: str = "mg1") -> str:
    allowed = sweepable_variables_general(distribution, model)
    if variable not in allowed:
        raise QueueValidationError(
            f"Para o {_label(model)} com distribuição {distribution}, a variável varrida deve ser "
            f"uma de: {', '.join(allowed)}.",
            "variable",
        )
    return str(variable)


def validate_mg1_variable(distribution: str, variable: object) -> str:
    return validate_general_variable(distribution, variable, "mg1")


def _servers_of(model: str, servers: object, *, required: bool = True) -> int | None:
    """Servidores do ponto base: 1 no M/G/1; no M/G/c, o valor informado (obrigatório se `required`)."""
    if model != "mgc":
        return 1
    if servers is None:
        if required:
            raise QueueValidationError(
                "servers é obrigatório para o modelo mgc (a menos que seja o parâmetro varrido).", "servers"
            )
        return None
    return validate_servers(servers)


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


def general_experiment_metrics(
    model: str, lam: float, service: ServiceDistribution, servers: int = 1
) -> dict[str, float]:
    """Métricas do ponto: as do M/G/1 (com P0) ou as do M/G/c (com P(esperar), sem P0)."""
    if model == "mgc":
        return mgc_metrics(lam, service, servers).as_dict()
    return mg1_experiment_metrics(lam, service)


def evaluate_general_point(
    model: str, lam: float, service: ServiceDistribution, servers: int = 1
) -> PointEvaluation:
    try:
        return PointEvaluation(STATUS_OK, None, general_experiment_metrics(model, lam, service, servers))
    except UnstableSystemError as error:
        return PointEvaluation(STATUS_UNSTABLE, str(error), None)
    except QueueValidationError as error:
        return PointEvaluation(STATUS_INVALID, str(error), None)


def evaluate_mg1_point(lam: float, service: ServiceDistribution) -> PointEvaluation:
    return evaluate_general_point("mg1", lam, service, 1)


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


def run_general_sweep(
    model: str,
    distribution: str,
    values: ServiceValues,
    variable: str,
    start: float,
    end: float,
    step: float,
    *,
    lam: float | None = None,
    servers: int | None = None,
    simulation: SimulationSettings | None = None,
) -> SweepResult:
    """Varre `lambda`, `mu`, `servers` (M/G/c), `cv` ou `k` e calcula as métricas de cada ponto.

    `values` são os parâmetros do serviço do ponto base (os da API: mean ou mu, cv, k...); eles
    precisam formar uma distribuição válida. `servers` é o c fixo do M/G/c (o M/G/1 tem um só).
    Com `simulation`, cada ponto estável também é simulado, todos com a mesma semente (números
    aleatórios comuns).
    """
    if model not in GENERAL_MODELS:
        raise QueueValidationError(f"model deve ser um de: {', '.join(GENERAL_MODELS)}.", "model")
    variable = validate_general_variable(distribution, variable, model)
    grid = validate_range(variable, start, end, step)
    base_values = _identity_values(distribution, values)
    base = build_distribution(distribution, base_values)
    lam_fixed = None if variable == "lambda" else _require_lambda(lam)
    servers_fixed = _servers_of(model, servers, required=variable != "servers")

    fixed: dict[str, float] = {}
    if variable != "lambda":
        fixed["lambda"] = lam_fixed
    if variable in ("lambda", "cv", "k", "servers"):
        fixed["mu"] = base.mu
    if variable in ("lambda", "mu", "servers"):
        fixed["cv"] = base.cv
    if model == "mgc" and variable != "servers":
        fixed["servers"] = servers_fixed

    def lam_of(value: float) -> float:
        return float(value) if variable == "lambda" else lam_fixed

    def servers_of(value: float) -> int:
        return int(value) if variable == "servers" else servers_fixed

    services: list[ServiceDistribution | None] = []
    points: list[SweepPoint] = []
    for value in grid:
        service, error = _point_service(distribution, base_values, variable, float(value))
        services.append(service)
        if service is None:
            points.append(SweepPoint(float(value), STATUS_INVALID, error, 0.0, None, None))
            continue
        evaluation = evaluate_general_point(model, lam_of(value), service, servers_of(value))
        points.append(SweepPoint(
            value=float(value), status=evaluation.status, message=evaluation.message,
            offered_utilization=lam_of(value) * service.mean / servers_of(value),
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
                if model == "mgc":
                    summary = simulate_mgc(
                        lam_of(grid[i]), services[i], servers_of(grid[i]), T, reps, warmup, seed, level
                    ).summary
                else:
                    summary = simulate_mg1(lam_of(grid[i]), services[i], T, reps, warmup, seed, level).summary
            except InsufficientSampleError as error:
                points[i] = replace(points[i], message=str(error))
            else:
                points[i] = replace(points[i], simulation=summary)

    return SweepResult(
        model=model, variable=variable, fixed=fixed, points=points, simulation=used,
        service=base.describe(),
    )


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
    """Varredura do M/G/1 (um servidor): `run_general_sweep` com model="mg1"."""
    return run_general_sweep(
        "mg1", distribution, values, variable, start, end, step, lam=lam, simulation=simulation
    )


# ---------- sensibilidade ----------

def _general_side(
    model: str, distribution: str, values: ServiceValues, lam: float, servers: int,
    name: str, value: float,
) -> SensitivitySide:
    if name == "k" and value < 1:
        return SensitivitySide(value, STATUS_INVALID, "k ficaria menor que 1.", None)
    if name == "servers" and value < 1:
        return SensitivitySide(value, STATUS_INVALID, "servers ficaria menor que 1.", None)
    lam_p = value if name == "lambda" else lam
    servers_p = int(value) if name == "servers" else servers
    service, error = _point_service(distribution, values, name, value)
    if service is None:
        return SensitivitySide(value, STATUS_INVALID, error, None)
    evaluation = evaluate_general_point(model, lam_p, service, servers_p)
    return SensitivitySide(value, evaluation.status, evaluation.message, evaluation.metrics)


def run_general_sensitivity(
    model: str, distribution: str, values: ServiceValues, lam: float,
    delta_pct: float = 10.0, servers: int | None = None,
) -> SensitivityResult:
    """Sensibilidade a λ, μ, c (M/G/c) e à variabilidade do serviço (CV, ou k no Erlang).

    O ponto base precisa ser estável (ρ < 1). λ, μ e CV variam ±delta_pct %; c e k variam ±1.
    """
    if model not in GENERAL_MODELS:
        raise QueueValidationError(f"model deve ser um de: {', '.join(GENERAL_MODELS)}.", "model")
    delta = validate_delta_pct(delta_pct)
    lam_v = validate_positive_finite("λ", lam)
    servers_v = _servers_of(model, servers)
    base_values = _identity_values(distribution, values)
    base_service = build_distribution(distribution, base_values)
    base_metrics = general_experiment_metrics(model, lam_v, base_service, servers_v)   # levanta se ρ ≥ 1

    base: dict[str, float] = {"lambda": lam_v, "mu": base_service.mu}
    if model == "mgc":
        base["servers"] = float(servers_v)
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
    if model == "mgc":
        perturbations.append(("servers", "units", servers_v - 1, servers_v + 1))
    if shape == "cv":
        perturbations.append(("cv", "percent", _clean(base["cv"] * (1 - factor)), _clean(base["cv"] * (1 + factor))))
    elif shape == "k":
        perturbations.append(("k", "units", base["k"] - 1, base["k"] + 1))

    parameters = []
    for name, kind, low_value, high_value in perturbations:
        low = _general_side(model, distribution, base_values, lam_v, servers_v, name, low_value)
        high = _general_side(model, distribution, base_values, lam_v, servers_v, name, high_value)
        parameters.append(ParameterSensitivity(
            name=name, base_value=base[name], perturbation=kind, low=low, high=high,
            effects=_effects(base_metrics, base[name], low, high),
        ))
    return SensitivityResult(
        model=model, delta_pct=delta, base=base, base_metrics=base_metrics, parameters=parameters,
        service=base_service.describe(),
    )


def run_mg1_sensitivity(
    distribution: str, values: ServiceValues, lam: float, delta_pct: float = 10.0
) -> SensitivityResult:
    """Sensibilidade do M/G/1: `run_general_sensitivity` com model="mg1"."""
    return run_general_sensitivity("mg1", distribution, values, lam, delta_pct)


# ---------- comparação de distribuições ----------

@dataclass(frozen=True)
class ServiceSeries:
    service: dict                      # descrição da distribuição (média, CV, parâmetros)
    points: list[SweepPoint]


@dataclass(frozen=True)
class ServicesComparisonResult:
    model: str
    series: list[ServiceSeries]
    servers: int | None = None         # só no M/G/c: o c fixo da comparação

    def as_dict(self) -> dict:
        return asdict(self)


def validate_service_list(specs: object) -> list[tuple[str, dict]]:
    if not isinstance(specs, (list, tuple)) or not 2 <= len(specs) <= MAX_COMPARED_SERVICES:
        raise QueueValidationError(
            f"services deve ter de 2 a {MAX_COMPARED_SERVICES} distribuições.", "services"
        )
    return list(specs)


def run_services_comparison(
    services: list[tuple[str, dict]], start: float, end: float, step: float,
    *, model: str = "mg1", servers: int | None = None,
) -> ServicesComparisonResult:
    """Compara distribuições de serviço, variando λ na mesma faixa para todas.

    Cada item é (distribuição, parâmetros). Uma distribuição que satura antes das outras só tem
    pontos instáveis a partir do seu ρ = 1; as demais séries continuam. No M/G/c, `servers` fixa
    o c da comparação (com c = 1 o resultado é o do M/G/1).
    """
    if model not in GENERAL_MODELS:
        raise QueueValidationError(f"model deve ser um de: {', '.join(GENERAL_MODELS)}.", "model")
    specs = validate_service_list(services)
    servers_v = _servers_of(model, servers)
    built = [build_distribution(key, _identity_values(key, values)) for key, values in specs]
    series = []
    for service in built:
        result = run_general_sweep(
            model, service.key, _canonical(service), "lambda", start, end, step, servers=servers_v
        )
        series.append(ServiceSeries(service.describe(), result.points))
    return ServicesComparisonResult(model=model, series=series, servers=servers_v if model == "mgc" else None)


def run_general_server_comparison(
    distribution: str, values: ServiceValues, servers_list: list[int],
    start: float, end: float, step: float,
) -> ServerComparisonResult:
    """Compara o M/G/c com c servidores diferentes e o mesmo serviço, variando λ na mesma faixa.

    Cada servidor mantém o serviço dado (mais servidores somam capacidade). Uma série que satura
    antes das outras só tem pontos instáveis a partir do seu ρ = 1; as demais continuam.
    """
    from app.domain.validation.experiments import validate_server_list   # evita ciclo na importação

    cs = validate_server_list(servers_list)
    base_values = _identity_values(distribution, values)
    base = build_distribution(distribution, base_values)
    series = [
        ServerSeries(c, run_general_sweep(
            "mgc", distribution, base_values, "lambda", start, end, step, servers=c
        ).points)
        for c in cs
    ]
    return ServerComparisonResult(
        model="mgc", mu=base.mu, capacity=None, series=series, service=base.describe()
    )


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
