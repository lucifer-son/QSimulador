"""Comparação analítico × simulação do Erlang-B e do M/G/c (Fase 10).

Reaproveita `compare_metrics` da Fase 4. No Erlang-B, o motor é o do M/M/c/K com K = c.
No M/G/c, o analítico é a aproximação de Allen–Cunneen, então o erro da comparação mostra
também o erro da própria aproximação.
"""

from dataclasses import asdict, dataclass

from app.analysis.comparison import MetricComparison, compare_metrics
from app.analytical.erlangb import erlangb_metrics
from app.analytical.mgc import mgc_metrics
from app.domain.service.distributions import ServiceDistribution
from app.simulation.mgc import simulate_mgc
from app.simulation.mmck import simulate_mmck
from app.simulation.results import QUEUE_METRIC_NAMES

# Abaixo disto, "sistema vazio" é raro demais para a simulação observar (com a = 20 e c = 15,
# P₀ ≈ 1e-8): a comparação seria ruído, não informação. O valor analítico continua no /calculate.
MIN_OBSERVABLE_P0 = 1e-4

# O M/G/c não define P₀ (a aproximação só dá L, Lq, W, Wq e P(esperar)).
MGC_METRIC_NAMES = ("rho", "L", "Lq", "W", "Wq", "throughput", "p_wait")


@dataclass(frozen=True)
class Phase10Comparison:
    lam: float
    servers: int
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    metrics: dict[str, MetricComparison]
    all_within_ci: bool | None
    max_relative_error_pct: float | None
    service: dict | None = None     # só no M/G/c
    mu: float | None = None         # só no Erlang-B

    def as_dict(self) -> dict:
        return asdict(self)


def _summarize(metrics: dict[str, MetricComparison]) -> tuple[bool | None, float | None]:
    flags = [m.within_ci for m in metrics.values()]
    errors = [m.relative_error_pct for m in metrics.values()]
    return (
        None if any(f is None for f in flags) else all(flags),
        None if any(e is None for e in errors) else max(errors),
    )


def compare_erlangb(
    lam: float, mu: float, servers: int, simulation_time: float, replications: int = 10,
    warmup_time: float = 0.0, seed: int | None = None, confidence_level: float = 0.95,
) -> Phase10Comparison:
    """Erlang-B analítico × simulação do M/M/c/K com K = c (as nove métricas)."""
    sim = simulate_mmck(
        lam, mu, servers, servers, simulation_time, replications, warmup_time, seed, confidence_level
    )
    analytical = erlangb_metrics(lam, mu, servers).as_dict()
    names = tuple(n for n in QUEUE_METRIC_NAMES if n != "p0" or analytical["p0"] >= MIN_OBSERVABLE_P0)
    metrics = compare_metrics(analytical, sim.summary, names)
    within, error = _summarize(metrics)
    return Phase10Comparison(
        lam=sim.lam, mu=sim.mu, servers=sim.servers, simulation_time=sim.simulation_time,
        warmup_time=sim.warmup_time, replications=sim.replications, seed=sim.seed,
        confidence_level=sim.confidence_level, metrics=metrics, all_within_ci=within,
        max_relative_error_pct=error,
    )


def compare_mgc(
    lam: float, service: ServiceDistribution, servers: int, simulation_time: float,
    replications: int = 10, warmup_time: float = 0.0, seed: int | None = None,
    confidence_level: float = 0.95,
) -> Phase10Comparison:
    """M/G/c (Allen–Cunneen) × simulação, nas sete métricas que a aproximação define."""
    sim = simulate_mgc(lam, service, servers, simulation_time, replications, warmup_time, seed, confidence_level)
    analytical = mgc_metrics(lam, service, servers).as_dict()
    metrics = compare_metrics(analytical, sim.summary, MGC_METRIC_NAMES)
    within, error = _summarize(metrics)
    return Phase10Comparison(
        lam=sim.lam, servers=sim.servers, simulation_time=sim.simulation_time,
        warmup_time=sim.warmup_time, replications=sim.replications, seed=sim.seed,
        confidence_level=sim.confidence_level, metrics=metrics, all_within_ci=within,
        max_relative_error_pct=error, service=sim.service,
    )
