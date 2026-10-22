"""Análise de sensibilidade (Fase 6): quanto cada métrica muda quando um parâmetro é perturbado.

Parte de um ponto base estável e perturba um parâmetro por vez. λ e μ variam ±delta_pct %;
c e K, que são inteiros, variam ±1 unidade. Para cada métrica, devolve a variação percentual
nos dois lados e a elasticidade (variação % da métrica por 1 % de variação do parâmetro).
Um lado que sai do regime estável ou do domínio do modelo é sinalizado, sem derrubar a análise.
"""

from dataclasses import asdict, dataclass

from app.domain.validation.errors import QueueValidationError
from app.domain.validation.experiments import (
    GENERAL_SERVICE_MODELS,
    USES_CAPACITY,
    USES_SERVERS,
    validate_delta_pct,
    validate_fixed_parameters,
    validate_model,
)
from app.experiments.points import STATUS_INVALID, STATUS_OK, analytical_metrics, evaluate_point


@dataclass(frozen=True)
class SensitivitySide:
    value: float
    status: str                         # "ok" | "unstable" | "invalid"
    message: str | None
    metrics: dict[str, float] | None


@dataclass(frozen=True)
class MetricEffect:
    low_change_pct: float | None        # variação da métrica quando o parâmetro diminui
    high_change_pct: float | None       # variação da métrica quando o parâmetro aumenta
    elasticity: float | None            # (ΔM/M) / (Δp/p), com os dois lados


@dataclass(frozen=True)
class ParameterSensitivity:
    name: str                           # "lambda" | "mu" | "servers" | "capacity"
    base_value: float
    perturbation: str                   # "percent" (λ, μ) ou "units" (c, K: ±1)
    low: SensitivitySide
    high: SensitivitySide
    effects: dict[str, MetricEffect]


@dataclass(frozen=True)
class SensitivityResult:
    model: str
    delta_pct: float
    base: dict[str, float]              # parâmetros do ponto base (nomes da API)
    base_metrics: dict[str, float]
    parameters: list[ParameterSensitivity]
    service: dict | None = None         # só no M/G/1: descrição do serviço do ponto base

    def as_dict(self) -> dict:
        return asdict(self)


def change_pct(value: float, base: float) -> float | None:
    """Variação percentual de `value` em relação a `base`; None quando a base é zero e o valor não."""
    if base == 0:
        return 0.0 if value == 0 else None
    return (value - base) / abs(base) * 100


def _clean(value: float) -> float:
    return float(f"{value:.12g}")


def run_sensitivity(
    model: str,
    lam: float,
    mu: float,
    servers: int | None = None,
    capacity: int | None = None,
    delta_pct: float = 10.0,
) -> SensitivityResult:
    """Sensibilidade das métricas aos parâmetros do modelo, em torno do ponto base.

    O ponto base precisa ser válido (λ < c·μ na fila ilimitada), senão levanta o mesmo erro
    do /calculate. Levanta QueueValidationError para parâmetros inválidos.
    """
    model = validate_model(model)
    if model in GENERAL_SERVICE_MODELS:
        raise QueueValidationError(
            f"O modelo {model} usa o serviço geral: a sensibilidade dele exige `service`.", "service"
        )
    delta = validate_delta_pct(delta_pct)
    lam_v, mu_v, servers_v, capacity_v = validate_fixed_parameters(
        model, None, lam, mu, servers, capacity
    )
    base_metrics = analytical_metrics(model, lam_v, mu_v, servers_v, capacity_v)

    base: dict[str, float] = {"lambda": lam_v, "mu": mu_v}
    if USES_SERVERS[model]:
        base["servers"] = servers_v
    if USES_CAPACITY[model]:
        base["capacity"] = capacity_v

    factor = delta / 100
    perturbations: list[tuple[str, str, float, float]] = [
        ("lambda", "percent", _clean(lam_v * (1 - factor)), _clean(lam_v * (1 + factor))),
        ("mu", "percent", _clean(mu_v * (1 - factor)), _clean(mu_v * (1 + factor))),
    ]
    if USES_SERVERS[model]:
        perturbations.append(("servers", "units", servers_v - 1, servers_v + 1))
    if USES_CAPACITY[model]:
        perturbations.append(("capacity", "units", capacity_v - 1, capacity_v + 1))

    base_point = {"lambda": lam_v, "mu": mu_v, "servers": servers_v, "capacity": capacity_v}
    parameters = []
    for name, kind, low_value, high_value in perturbations:
        low = _side_at(model, base_point, name, low_value)
        high = _side_at(model, base_point, name, high_value)
        parameters.append(ParameterSensitivity(
            name=name,
            base_value=base[name],
            perturbation=kind,
            low=low,
            high=high,
            effects=_effects(base_metrics, base[name], low, high),
        ))

    return SensitivityResult(
        model=model, delta_pct=delta, base=base, base_metrics=base_metrics, parameters=parameters
    )


def _side_at(model: str, base_point: dict, name: str, value: float) -> SensitivitySide:
    """Calcula o ponto base com `name` trocado por `value`, sinalizando o que não for válido."""
    if name in ("servers", "capacity") and value < 1:
        return SensitivitySide(value, STATUS_INVALID, f"{name} ficaria menor que 1.", None)
    point = {**base_point, name: value}
    evaluation = evaluate_point(
        model, point["lambda"], point["mu"], point["servers"], point["capacity"]
    )
    return SensitivitySide(value, evaluation.status, evaluation.message, evaluation.metrics)


def _effects(
    base_metrics: dict[str, float], base_value: float, low: SensitivitySide, high: SensitivitySide
) -> dict[str, MetricEffect]:
    effects: dict[str, MetricEffect] = {}
    both_ok = low.status == STATUS_OK and high.status == STATUS_OK
    param_span = (high.value - low.value) / base_value
    for name, base in base_metrics.items():
        low_change = change_pct(low.metrics[name], base) if low.metrics else None
        high_change = change_pct(high.metrics[name], base) if high.metrics else None
        elasticity = None
        if both_ok and base != 0:
            elasticity = ((high.metrics[name] - low.metrics[name]) / base) / param_span
        effects[name] = MetricEffect(low_change, high_change, elasticity)
    return effects
