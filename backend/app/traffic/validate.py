"""Validação do cenário de referência contra as contagens do vídeo (Fase 13.1).

Simula o plano observado com as chegadas do vídeo (o número de chegadas de cada intervalo é o
observado; só o instante dentro do intervalo é sorteado) e compara, intervalo a
intervalo, a fila e as saídas simuladas com as observadas. Resultado: erros (viés, erro médio
absoluto e quadrático) e a cobertura da **faixa de variação simulada** (percentis entre réplicas;
não é um IC da média). **Não é um teste de hipótese e não há limite de aprovação**: os números
mostram o quanto o modelo reproduz o que foi observado, e quem decide se basta é o analista.

Dados ausentes ficam de fora da comparação (e são contados). Filas marcadas como parcialmente
visíveis (`queue_visible = não`) também ficam de fora.
"""

import math
from dataclasses import replace

import numpy as np
from scipy import stats

from app.traffic.engine import simulate_replication
from app.traffic.metrics import queue_at
from app.traffic.plan import APPROACH_KEYS, ArrivalProfile, Intersection
from app.traffic.run import Settings
from app.traffic.video import Session


def _band(matrix: np.ndarray, level: float) -> dict:
    lo, hi = (1 - level) / 2 * 100, (1 + level) / 2 * 100
    return {"mean": matrix.mean(axis=0), "low": np.percentile(matrix, lo, axis=0), "high": np.percentile(matrix, hi, axis=0)}


def _errors(observed: np.ndarray, band: dict) -> dict | None:
    if len(observed) == 0:
        return None
    diff = band["mean"] - observed
    inside = (observed >= band["low"] - 1e-9) & (observed <= band["high"] + 1e-9)
    return {
        "n": int(len(observed)), "bias": float(diff.mean()), "mae": float(np.abs(diff).mean()),
        "rmse": float(math.sqrt((diff ** 2).mean())), "coverage": float(inside.mean()),
    }


def _finite(x):
    return None if x is None or (isinstance(x, float) and not math.isfinite(x)) else x


def with_observed_counts(session: Session, inter: Intersection) -> Intersection:
    """Troca o perfil de chegadas de cada aproximação pelas contagens observadas (número fixo por intervalo)."""
    approaches = []
    for app, a in zip(inter.approaches, session.approach_ids):
        items = session.counts[a]
        profile = ArrivalProfile(
            tuple(d["start"] for d in items), tuple(d["arrivals"] / (d["end"] - d["start"]) for d in items),
            items[-1]["end"], counts=tuple(d["arrivals"] for d in items))
        approaches.append(replace(app, profile=profile))
    return replace(inter, approaches=(approaches[0], approaches[1]))


def validate_session(session: Session, inter: Intersection, settings: Settings) -> dict:
    """`inter` fornece o plano e os parâmetros de descarga; as chegadas vêm sempre das contagens observadas."""
    inter = with_observed_counts(session, inter)
    T, reps = settings.simulation_time, settings.replications
    runs = [simulate_replication(inter, T, settings.seed, r) for r in range(reps)]
    level = settings.confidence_level
    out = {"approaches": {}, "settings": {
        "simulation_time": T, "replications": reps, "seed": settings.seed, "band_level": level,
        "note": ("A faixa é o intervalo central de {:.0%} dos valores simulados entre réplicas (variação do próprio "
                 "processo), não um IC da média. Não há limite de aprovação: os erros descrevem o quanto o modelo reproduz o observado.").format(level),
    }, "notes": []}

    for i, (key, a) in enumerate(zip(APPROACH_KEYS, session.approach_ids)):
        items = [d for d in session.counts[a] if d["end"] <= T + 1e-9]
        starts = np.array([d["start"] for d in items])
        ends = np.array([d["end"] for d in items])
        q_sim = np.stack([queue_at(run[i], ends) for run in runs])
        dep_sim = np.stack([
            np.searchsorted(run[i].departures, ends, side="left") - np.searchsorted(run[i].departures, starts, side="left")
            for run in runs]).astype(float)
        q_band, d_band = _band(q_sim, level), _band(dep_sim, level)

        q_obs = np.array([d["queue"] if (d["queue"] is not None and d["queue_visible"] is not False) else math.nan for d in items], float)
        d_obs = np.array([d["departures"] if d["departures"] is not None else math.nan for d in items], float)
        q_ok, d_ok = ~np.isnan(q_obs), ~np.isnan(d_obs)

        rows = []
        for j, d in enumerate(items):
            rows.append({
                "start": d["start"], "end": d["end"],
                "queue": {"observed": _finite(None if not q_ok[j] else float(q_obs[j])),
                          "mean": float(q_band["mean"][j]), "low": float(q_band["low"][j]), "high": float(q_band["high"][j])},
                "departures": {"observed": _finite(None if not d_ok[j] else float(d_obs[j])),
                               "mean": float(d_band["mean"][j]), "low": float(d_band["low"][j]), "high": float(d_band["high"][j])},
            })

        total_sim = dep_sim.sum(axis=1)
        total_obs = float(np.nansum(d_obs)) if d_ok.all() else None
        entry = {
            "approach_id": a, "intervals": rows,
            "queue": _errors(q_obs[q_ok], {k: v[q_ok] for k, v in q_band.items()}),
            "departures": _errors(d_obs[d_ok], {k: v[d_ok] for k, v in d_band.items()}),
            "departures_total": {
                "observed": total_obs, "mean": float(total_sim.mean()),
                "low": float(np.percentile(total_sim, (1 - level) / 2 * 100)), "high": float(np.percentile(total_sim, (1 + level) / 2 * 100)),
                "relative_error": None if not total_obs else float((total_sim.mean() - total_obs) / total_obs),
            },
            "excluded": {"queue": int((~q_ok).sum()), "departures": int((~d_ok).sum())},
            "delay": None,
        }
        if (~q_ok).any():
            out["notes"].append(f"{a}: {int((~q_ok).sum())} intervalo(s) sem fila observada utilizável (ausente ou parcialmente visível) ficaram fora da comparação da fila.")
        if (~d_ok).any():
            out["notes"].append(f"{a}: {int((~d_ok).sum())} intervalo(s) sem contagem de saídas ficaram fora da comparação das saídas.")

        if session.tracks is not None and session.tracks.get(a):
            waits = np.array([c - q for q, c, ok in session.tracks[a] if ok and c >= q], float)
            if len(waits) >= 2:
                half = stats.t.ppf((1 + level) / 2, len(waits) - 1) * waits.std(ddof=1) / math.sqrt(len(waits))
                sim_delays = []
                for run in runs:
                    arr, dep = run[i].arrivals[run[i].n_initial:], run[i].departures[run[i].n_initial:]
                    done = dep < T
                    sim_delays.append(float((dep[done] - arr[done]).mean()) if done.any() else math.nan)
                sim = np.array(sim_delays)
                sim = sim[~np.isnan(sim)]
                entry["delay"] = {
                    "observed_mean": float(waits.mean()), "observed_ci": [float(waits.mean() - half), float(waits.mean() + half)],
                    "observed_n": int(len(waits)), "simulated_mean": float(sim.mean()),
                    "simulated_low": float(np.percentile(sim, (1 - level) / 2 * 100)),
                    "simulated_high": float(np.percentile(sim, (1 + level) / 2 * 100)),
                    "note": "O observado vem só dos veículos acompanhados até o fim (amostra que pode excluir os mais lentos).",
                }
        out["approaches"][key] = entry
    return out
