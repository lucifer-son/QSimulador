"""Métricas de uma réplica do cruzamento (Fase 13.1).

Janela de medição [w, T): w é o warm-up (0 para reproduzir uma gravação). Definições:

- **atraso** do veículo: instante em que cruza a linha de retenção − instante em que chegou à fila
  (0 quando não precisa esperar). Só entram os veículos que chegaram em [w, T); os da fila inicial
  esperavam desde antes da gravação e ficam de fora do atraso (mas ocupam a fila e a capacidade).
- **atraso (concluídos)**: média dos que cruzaram até T. **atraso (com pendentes)**: inclui os que
  ainda esperavam em T, contados só até T (limite inferior do atraso verdadeiro). Se a fila cresce,
  o primeiro número parece melhor do que a realidade; por isso os dois são sempre mostrados.
- **fila**: veículos que chegaram e ainda não cruzaram (inclui a fila inicial).
- **ciclos com fila**: fração dos ciclos com o fim do verde dentro da janela em que sobrou fila
  ao fim do verde utilizável (falha de ciclo).
"""

import math
from dataclasses import dataclass

import numpy as np

from app.traffic.engine import FREE_EPS, ApproachRun
from app.traffic.plan import Intersection

APPROACH_METRICS = (
    "delay", "delay_censored", "queue_mean", "queue_max", "queue_end", "throughput",
    "stopped_fraction", "overflow_cycles", "arrivals", "departures", "pending",
)
INTERSECTION_METRICS = ("delay", "delay_censored", "throughput", "queue_mean", "arrivals", "departures", "pending")


@dataclass(frozen=True)
class ApproachSample:
    """Métricas de uma aproximação em uma réplica (NaN quando não há veículos para medir)."""

    values: dict[str, float]
    delay_sum: float          # soma dos atrasos concluídos (para ponderar o cruzamento)
    delay_censored_sum: float
    measured: int             # veículos medidos (chegaram em [w, T))


def queue_profile(run: ApproachRun, w: float, horizon: float) -> tuple[float, float, int, int]:
    """(fila média no tempo, fila máxima, fila em w, fila em T) em [w, T)."""
    deps = run.departures[run.departures < horizon]
    times = np.concatenate([run.arrivals[run.arrivals < horizon], deps])
    delta = np.concatenate([np.ones(int((run.arrivals < horizon).sum())), -np.ones(len(deps))])
    order = np.lexsort((-delta, times))      # no mesmo instante a chegada vem antes da saída
    times, delta = times[order], delta[order]
    level = np.cumsum(delta)
    before = int((times < w).sum())
    q_w = float(level[before - 1]) if before else 0.0
    inside_t = times[before:]
    inside_level = level[before:]
    edges = np.concatenate([[w], inside_t, [horizon]])
    levels = np.concatenate([[q_w], inside_level])
    area = float(np.sum(levels * np.diff(edges)))
    q_max = float(levels.max()) if len(levels) else q_w
    q_end = float(levels[-1])
    return area / (horizon - w), q_max, int(q_w), int(q_end)


def queue_at(run: ApproachRun, grid: np.ndarray) -> np.ndarray:
    """Fila (chegaram e ainda não cruzaram) em cada instante da grade."""
    arrived = np.searchsorted(run.arrivals, grid, side="right")
    crossed = np.searchsorted(run.departures, grid, side="right")
    return (arrived - crossed).astype(float)


def approach_sample(inter: Intersection, index: int, run: ApproachRun, w: float, horizon: float) -> ApproachSample:
    arr = run.arrivals[run.n_initial:]
    dep = run.departures[run.n_initial:]
    measured_mask = (arr >= w) & (arr < horizon)
    arr_m, dep_m = arr[measured_mask], dep[measured_mask]
    done = dep_m < horizon
    waits_done = dep_m[done] - arr_m[done]
    pending_waits = horizon - arr_m[~done]
    n_meas, n_done, n_pend = len(arr_m), int(done.sum()), int((~done).sum())

    delay_sum = float(waits_done.sum())
    cens_sum = delay_sum + float(pending_waits.sum())
    stopped = int((waits_done > FREE_EPS).sum()) + n_pend

    q_mean, q_max, _, q_end = queue_profile(run, w, horizon)

    # ciclos com fila: fim do verde utilizável dentro da janela de medição
    phase, app = inter.signal.phases[index], inter.approaches[index]
    cycle = inter.signal.cycle
    gs0 = inter.signal.green_start(index)
    window = phase.green + app.amber_usable
    k_lo = math.ceil((w - gs0 - window) / cycle)
    k_hi = math.ceil((horizon - gs0 - window) / cycle) - 1
    if k_hi >= k_lo:
        ends = gs0 + window + cycle * np.arange(k_lo, k_hi + 1)
        residual = queue_at(run, ends)
        overflow = float(np.mean(residual > 0))
    else:
        overflow = math.nan

    deps_window = int(((run.departures >= w) & (run.departures < horizon)).sum())
    span = horizon - w
    nan = math.nan
    values = {
        "delay": delay_sum / n_done if n_done else nan,
        "delay_censored": cens_sum / n_meas if n_meas else nan,
        "queue_mean": q_mean, "queue_max": q_max, "queue_end": float(q_end),
        "throughput": deps_window / span,
        "stopped_fraction": stopped / n_meas if n_meas else nan,
        "overflow_cycles": overflow,
        "arrivals": float(n_meas), "departures": float(deps_window), "pending": float(n_pend),
    }
    return ApproachSample(values, delay_sum, cens_sum, n_meas)


def intersection_values(samples: tuple[ApproachSample, ApproachSample], w: float, horizon: float) -> dict[str, float]:
    """Métricas do cruzamento: atrasos ponderados pelos veículos medidos de cada aproximação."""
    nan = math.nan
    done = sum(s.values["arrivals"] - s.values["pending"] for s in samples)
    meas = sum(s.measured for s in samples)
    return {
        "delay": sum(s.delay_sum for s in samples) / done if done else nan,
        "delay_censored": sum(s.delay_censored_sum for s in samples) / meas if meas else nan,
        "throughput": sum(s.values["throughput"] for s in samples),
        "queue_mean": sum(s.values["queue_mean"] for s in samples),
        "arrivals": sum(s.values["arrivals"] for s in samples),
        "departures": sum(s.values["departures"] for s in samples),
        "pending": sum(s.values["pending"] for s in samples),
    }


def replication_metrics(inter: Intersection, runs: tuple[ApproachRun, ApproachRun], w: float, horizon: float):
    samples = tuple(approach_sample(inter, i, run, w, horizon) for i, run in enumerate(runs))
    return samples, intersection_values(samples, w, horizon)
