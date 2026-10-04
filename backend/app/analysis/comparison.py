"""Comparação entre o modelo analítico e a simulação.

`compare_metrics` é uma função pura (compara números já calculados) e
`compare_mm1` orquestra o fluxo completo: analítico + simulação + comparação.
"""

from collections.abc import Mapping
from dataclasses import asdict, dataclass

from app.analytical.mm1 import mm1_metrics
from app.simulation.mm1 import simulate_mm1
from app.simulation.results import METRIC_NAMES, MetricSummary


@dataclass(frozen=True)
class MetricComparison:
    """Comparação de uma métrica entre analítico e simulação."""

    analytical: float
    simulated_mean: float
    ci_low: float | None            # None com 1 réplica (sem intervalo)
    ci_high: float | None
    absolute_error: float           # |simulado - analítico|
    relative_error_pct: float | None  # em % do valor analítico
    within_ci: bool | None          # o valor analítico está dentro do IC?


@dataclass(frozen=True)
class ComparisonResult:
    lam: float
    mu: float
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    metrics: dict[str, MetricComparison]
    # True se todas as métricas ficaram dentro do IC; None se não há IC (1 réplica).
    all_within_ci: bool | None
    max_relative_error_pct: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def relative_error_pct(value: float, reference: float) -> float | None:
    """Erro relativo percentual de `value` em relação a `reference`.

    Devolve None quando o erro relativo é indefinido (referência zero e
    valor diferente de zero).
    """
    if reference == 0:
        return 0.0 if value == 0 else None
    return abs(value - reference) / abs(reference) * 100


def compare_metrics(
    analytical: Mapping[str, float],
    summary: Mapping[str, MetricSummary],
) -> dict[str, MetricComparison]:
    """Compara, métrica a métrica, valores analíticos e o resumo da simulação."""
    comparisons: dict[str, MetricComparison] = {}
    for name in METRIC_NAMES:
        exact = analytical[name]
        s = summary[name]
        has_ci = s.ci_low is not None and s.ci_high is not None
        comparisons[name] = MetricComparison(
            analytical=exact,
            simulated_mean=s.mean,
            ci_low=s.ci_low,
            ci_high=s.ci_high,
            absolute_error=abs(s.mean - exact),
            relative_error_pct=relative_error_pct(s.mean, exact),
            within_ci=bool(s.ci_low <= exact <= s.ci_high) if has_ci else None,
        )
    return comparisons


def compare_mm1(
    lam: float,
    mu: float,
    simulation_time: float,
    replications: int = 10,
    warmup_time: float = 0.0,
    seed: int | None = None,
    confidence_level: float = 0.95,
) -> ComparisonResult:
    """Calcula o M/M/1 analítico, simula e compara os resultados.

    Os parâmetros e os erros levantados são os mesmos de `simulate_mm1`.
    Em regime estável, a vazão de saída é igual a λ, então ela entra na
    comparação com valor analítico λ.
    """
    simulation = simulate_mm1(
        lam, mu, simulation_time, replications, warmup_time, seed, confidence_level
    )
    analytical = {**mm1_metrics(lam, mu).as_dict(), "throughput": simulation.lam}
    metrics = compare_metrics(analytical, simulation.summary)

    flags = [m.within_ci for m in metrics.values()]
    all_within = None if any(f is None for f in flags) else all(flags)
    errors = [m.relative_error_pct for m in metrics.values()]
    max_error = None if any(e is None for e in errors) else max(errors)

    return ComparisonResult(
        lam=simulation.lam,
        mu=simulation.mu,
        simulation_time=simulation.simulation_time,
        warmup_time=simulation.warmup_time,
        replications=simulation.replications,
        seed=simulation.seed,
        confidence_level=simulation.confidence_level,
        metrics=metrics,
        all_within_ci=all_within,
        max_relative_error_pct=max_error,
    )
