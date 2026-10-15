"""Comparação tripla: medido × analítico × simulação (RF-24, simulação opcional da Fase 7).

Parte da comparação já existente (`compare_chosen`, que valida os parâmetros e calcula o
analítico contra a medição) e acrescenta, em cada métrica de cada nível, a média simulada
com seu intervalo de confiança. Para o nível i, a simulação usa a semente `seed + i`, então
o resultado é reproduzível e os níveis são independentes entre si.

Sistema fechado usa a simulação de população finita (N do nível, Z e μ informados);
sistema aberto usa λ̂ do nível, μ, c e a capacidade, como no analítico.
"""

import secrets
from dataclasses import dataclass

from app.analysis.comparison import relative_error_pct
from app.realdata.metrics import LoadLevel
from app.realdata.recommendation import CANDIDATES, compare_chosen
from app.simulation.finite_population import simulate_finite_population
from app.simulation.mmck import simulate_mmck


@dataclass(frozen=True)
class SimulationSettings:
    simulation_time: float
    replications: int = 10
    warmup_time: float = 0.0
    seed: int | None = None
    confidence_level: float = 0.95


def compare_simulated(
    key: str,
    levels: list[LoadLevel],
    mu: float,
    settings: SimulationSettings,
    servers: int = 1,
    capacity: int | None = None,
    think_time: float | None = None,
) -> tuple[str, list[dict], dict]:
    """Devolve (notação, comparação por nível com colunas de simulação, configuração usada)."""
    notation, comparison = compare_chosen(key, levels, mu, servers, capacity, think_time)
    cand = next(c for c in CANDIDATES if c.key == key)
    c = servers if cand.multi_server else 1
    base_seed = settings.seed if settings.seed is not None else secrets.randbits(30)

    for i, (lv, row) in enumerate(zip(levels, comparison)):
        args = (settings.simulation_time, settings.replications, settings.warmup_time,
                base_seed + i, settings.confidence_level)
        if cand.family == "closed":
            sim = simulate_finite_population(lv.users, think_time, mu, c, *args)  # type: ignore[arg-type]
        else:
            sim = simulate_mmck(lv.metrics.arrival_rate, mu, c, capacity if cand.finite_capacity else None, *args)
        for name, metric in row["metrics"].items():
            summary = sim.summary.get(name)
            observed = metric["observed"]
            if summary is None:
                continue
            has_ci = summary.ci_low is not None and summary.ci_high is not None
            obs_low, obs_high = metric["observed_ci_low"], metric["observed_ci_high"]
            metric.update(
                simulated_mean=float(summary.mean),
                simulated_ci_low=float(summary.ci_low) if has_ci else None,
                simulated_ci_high=float(summary.ci_high) if has_ci else None,
                simulated_error_pct=relative_error_pct(summary.mean, observed),
                simulation_within_observed_ci=(
                    bool(obs_low <= summary.mean <= obs_high) if obs_low is not None and obs_high is not None else None
                ),
            )
    used = {
        "simulation_time": settings.simulation_time, "replications": settings.replications,
        "warmup_time": settings.warmup_time, "seed": base_seed, "confidence_level": settings.confidence_level,
    }
    return notation, comparison, used
