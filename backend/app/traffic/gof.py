"""Testes de hipótese da validação do cruzamento (Fase 13.2).

Todos comparam o observado no vídeo com o que o modelo simula. Nenhum tem valor padrão de tolerância: a
equivalência (TOST) só roda quando o analista informa a margem aceitável.

- `monte_carlo_gof`: aderência de uma série por intervalo (fila ou saídas). A estatística é a soma dos quadrados
  dos desvios em relação à média simulada. O p-valor compara a do observado com a de cada réplica (contra a média
  das outras), com a correção de escala (1 + 1/R) / (1 + 1/(R − 1)) para que os dois lados tenham a mesma variância
  sob H0. p = (1 + nº de réplicas com estatística ≥ a do observado) / (R + 1). Não supõe distribuição.
- `monte_carlo_bias`: o mesmo esquema com o desvio médio com sinal (observado − média simulada): detecta viés
  sistemático (fila ou saídas sempre acima ou abaixo), com bem mais poder que o desvio quadrático.
- `ks_and_mann_whitney`: KS de duas amostras e Mann-Whitney entre os atrasos observados e os simulados.
- `tost`: dois testes unilaterais (Schuirmann) para mostrar que a diferença cabe em ±margem.
- `holm`: correção de p-valores por Holm (controla a taxa de erro familiar).
"""

import math

import numpy as np
from scipy import stats

MIN_REPLICATIONS = 10      # abaixo disso o p-valor de Monte Carlo tem resolução ruim demais (1 / (R + 1))
MIN_DELAYS = 5


def holm(p_values: list[float]) -> list[float]:
    """p-valores ajustados por Holm (na ordem de entrada)."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    adjusted = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * p_values[i]))
        adjusted[i] = running
    return adjusted


def monte_carlo_gof(observed: np.ndarray, simulated: np.ndarray) -> dict | None:
    """`observed`: n intervalos (sem faltantes); `simulated`: R × n. None se não houver dados suficientes."""
    r = simulated.shape[0]
    if len(observed) < 3 or r < MIN_REPLICATIONS:
        return None
    total = simulated.sum(axis=0)
    mean_all = total / r
    t_obs = float(((observed - mean_all) ** 2).sum())
    loo_mean = (total[None, :] - simulated) / (r - 1)
    scale = (1 + 1 / r) / (1 + 1 / (r - 1))
    t_rep = ((simulated - loo_mean) ** 2).sum(axis=1) * scale
    p = float((1 + (t_rep >= t_obs - 1e-12).sum()) / (r + 1))
    return {"statistic": t_obs, "reference_median": float(np.median(t_rep)), "p_value": p, "n": int(len(observed)), "replications": int(r)}


def monte_carlo_bias(observed: np.ndarray, simulated: np.ndarray) -> dict | None:
    """Viés médio com sinal; p-valor bilateral por Monte Carlo (mesmo esquema de `monte_carlo_gof`)."""
    r = simulated.shape[0]
    if len(observed) < 3 or r < MIN_REPLICATIONS:
        return None
    total = simulated.sum(axis=0)
    d_obs = float((observed - total / r).mean())
    loo_mean = (total[None, :] - simulated) / (r - 1)
    scale = math.sqrt((1 + 1 / r) / (1 + 1 / (r - 1)))
    d_rep = (simulated - loo_mean).mean(axis=1) * scale
    p = float((1 + (np.abs(d_rep) >= abs(d_obs) - 1e-12).sum()) / (r + 1))
    return {"statistic": d_obs, "p_value": p, "n": int(len(observed)), "replications": int(r)}


def ks_and_mann_whitney(observed: np.ndarray, simulated: np.ndarray) -> dict | None:
    if len(observed) < MIN_DELAYS or len(simulated) < MIN_DELAYS:
        return None
    ks = stats.ks_2samp(observed, simulated)
    mw = stats.mannwhitneyu(observed, simulated, alternative="two-sided")
    return {
        "ks": {"statistic": float(ks.statistic), "p_value": float(ks.pvalue)},
        "mann_whitney": {"statistic": float(mw.statistic), "p_value": float(mw.pvalue)},
        "n_observed": int(len(observed)), "n_simulated": int(len(simulated)),
    }


def tost(difference: float, se: float, margin: float, alpha: float, df: float) -> dict | None:
    """H0: |diferença| ≥ margem. Equivalente se os dois testes unilaterais rejeitam ao nível alpha."""
    if not (se > 0 and math.isfinite(se) and margin > 0):
        return None
    p_low = float(stats.t.sf((difference + margin) / se, df))     # H0: diferença ≤ −margem
    p_high = float(stats.t.cdf((difference - margin) / se, df))   # H0: diferença ≥ +margem
    p = max(p_low, p_high)
    return {"difference": float(difference), "se": float(se), "margin": float(margin), "p_value": p,
            "alpha": alpha, "equivalent": bool(p < alpha), "df": float(df)}
