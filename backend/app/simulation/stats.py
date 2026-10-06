"""Estatísticas compartilhadas pelos simuladores."""

import numpy as np
from scipy import stats

from app.simulation.results import MetricSummary


def summarize(values: list[float], confidence_level: float) -> MetricSummary:
    """Média, desvio e intervalo de confiança (t de Student) entre réplicas."""
    n = len(values)
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean())
    if n < 2:
        return MetricSummary(mean=mean, std=None, ci_low=None, ci_high=None, n=n)
    std = float(arr.std(ddof=1))
    t_crit = float(stats.t.ppf((1 + confidence_level) / 2, df=n - 1))
    half = t_crit * std / np.sqrt(n)
    return MetricSummary(mean=mean, std=std, ci_low=mean - half, ci_high=mean + half, n=n)
