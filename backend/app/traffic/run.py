"""Executa as réplicas de um plano e resume (Fase 13.1)."""

import math
import secrets
from dataclasses import dataclass

import numpy as np
from scipy import stats

from app.domain.validation.errors import InsufficientSampleError, QueueValidationError
from app.domain.validation.simulation import validate_simulation_settings
from app.simulation.results import MetricSummary
from app.simulation.stats import summarize
from app.traffic.engine import simulate_replication
from app.traffic.metrics import (
    APPROACH_METRICS, INTERSECTION_METRICS, queue_at, replication_metrics,
)
from app.traffic.plan import (
    APPROACH_KEYS, MAX_SIMULATION_TIME, MAX_TRAFFIC_EXPECTED_ARRIVALS, Intersection, pt,
)

DEFAULT_SERIES_POINTS = 240
MAX_SERIES_POINTS = 2000


@dataclass(frozen=True)
class Settings:
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    series_step: float


def prepare_settings(
    inter: Intersection, *, simulation_time: object, replications: object = 10, warmup_time: object = 0.0,
    seed: object = None, confidence_level: object = 0.95, series_step: object = None,
    plans: int = 1,
) -> Settings:
    """Valida T, réplicas, semente e passo da série; confere o horizonte contra os perfis e o custo total."""
    if simulation_time is None:
        raise QueueValidationError("simulation_time é obrigatório.", "simulation_time")
    total_rate = sum(a.profile.mean_rate(float(simulation_time)) if isinstance(simulation_time, (int, float)) and simulation_time > 0 else a.profile.peak_rate()
                     for a in inter.approaches)
    T, reps, warmup, seed_v, level = validate_simulation_settings(
        total_rate, simulation_time, replications, warmup_time, seed, confidence_level)
    if T > MAX_SIMULATION_TIME:
        raise QueueValidationError(f"simulation_time passa do limite de {MAX_SIMULATION_TIME:g} s (24 h).", "simulation_time")
    for i, app in enumerate(inter.approaches):
        if app.profile.end is not None and T > app.profile.end + 1e-9:
            raise QueueValidationError(
                f"O perfil de chegadas de {app.name} cobre {app.profile.end:g} s, menos que simulation_time ({T:g} s).",
                f"approaches.{i}.profile")
    expected = sum(a.profile.expected_arrivals(T) + a.initial_queue for a in inter.approaches) * reps * plans
    if expected > MAX_TRAFFIC_EXPECTED_ARRIVALS:
        raise QueueValidationError(
            f"Simulação grande demais (~{pt(expected)} veículos esperados somando réplicas e planos; "
            f"limite {pt(MAX_TRAFFIC_EXPECTED_ARRIVALS)}). Reduza simulation_time, replications ou o número de planos.",
            "simulation_time")
    if seed_v is None:
        seed_v = secrets.randbits(32)
    span = T - warmup
    if series_step is None:
        step = span / DEFAULT_SERIES_POINTS
    else:
        if isinstance(series_step, bool) or not isinstance(series_step, (int, float)) or not math.isfinite(series_step) or series_step <= 0:
            raise QueueValidationError("series_step deve ser um número maior que zero.", "series_step")
        step = float(series_step)
        if span / step > MAX_SERIES_POINTS:
            raise QueueValidationError(
                f"series_step gera mais de {MAX_SERIES_POINTS} pontos; use um passo de pelo menos {span / MAX_SERIES_POINTS:.3g} s.",
                "series_step")
    return Settings(T, warmup, reps, seed_v, level, step)


@dataclass
class RunResult:
    approaches: dict[str, dict[str, MetricSummary | None]]
    intersection: dict[str, MetricSummary | None]
    raw: dict[str, np.ndarray]            # "a1.delay" -> valores por réplica (NaN onde não há amostra)
    series: dict | None


def _summary(values: np.ndarray, level: float) -> MetricSummary | None:
    ok = values[~np.isnan(values)]
    if len(ok) == 0:
        return None
    return summarize(ok.tolist(), level)


def grid_of(settings: Settings) -> np.ndarray:
    n = int(math.floor((settings.simulation_time - settings.warmup_time) / settings.series_step + 1e-9))
    return settings.warmup_time + settings.series_step * np.arange(n + 1)


def run_plan(inter: Intersection, settings: Settings, *, with_series: bool = True) -> RunResult:
    reps = settings.replications
    raw: dict[str, list[float]] = {f"{k}.{m}": [] for k in APPROACH_KEYS for m in APPROACH_METRICS}
    raw.update({f"x.{m}": [] for m in INTERSECTION_METRICS})
    grid = grid_of(settings) if with_series else None
    queues = [np.empty((reps, len(grid))) for _ in range(2)] if with_series else None

    for r in range(reps):
        runs = simulate_replication(inter, settings.simulation_time, settings.seed, r)
        samples, inter_vals = replication_metrics(inter, runs, settings.warmup_time, settings.simulation_time)
        for key, sample in zip(APPROACH_KEYS, samples):
            for m in APPROACH_METRICS:
                raw[f"{key}.{m}"].append(sample.values[m])
        for m in INTERSECTION_METRICS:
            raw[f"x.{m}"].append(inter_vals[m])
        if with_series:
            for i, run in enumerate(runs):
                queues[i][r] = queue_at(run, grid)

    arrays = {k: np.asarray(v, dtype=float) for k, v in raw.items()}
    if np.isnan(arrays["x.delay_censored"]).all():
        raise InsufficientSampleError(
            "Nenhum veículo chegou na janela de medição. Aumente simulation_time ou a taxa de chegada.", "simulation_time")
    level = settings.confidence_level
    approaches = {k: {m: _summary(arrays[f"{k}.{m}"], level) for m in APPROACH_METRICS} for k in APPROACH_KEYS}
    intersection = {m: _summary(arrays[f"x.{m}"], level) for m in INTERSECTION_METRICS}

    series = None
    if with_series:
        series = {"times": grid.tolist()}
        t_crit = float(stats.t.ppf((1 + level) / 2, df=reps - 1))
        for key, q in zip(APPROACH_KEYS, queues):
            mean = q.mean(axis=0)
            half = t_crit * q.std(axis=0, ddof=1) / math.sqrt(reps)
            series[key] = {"mean": mean.tolist(), "ci_low": np.maximum(mean - half, 0).tolist(), "ci_high": (mean + half).tolist()}
    return RunResult(approaches, intersection, arrays, series)
