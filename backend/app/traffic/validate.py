"""Validação do cenário de referência contra as contagens do vídeo (Fases 13.1 e 13.2).

Simula o plano observado com as chegadas do vídeo (o número de chegadas de cada intervalo é o
observado; só o instante dentro do intervalo é sorteado) e compara, intervalo a
intervalo, a fila e as saídas simuladas com as observadas. Resultado: erros (viés, erro médio
absoluto e quadrático) e a cobertura da **faixa de variação simulada** (percentis entre réplicas;
não é um IC da média). Os erros e a cobertura descrevem o quanto o modelo reproduz o observado; quem decide se basta é o analista.

Fase 13.2: além dos erros, o resultado traz `tests`, testes de hipótese com p-valor (corrigido por Holm entre
os testes de cada aproximação):

- **aderência da fila e das saídas por intervalo** (Monte Carlo): a estatística é a soma dos quadrados dos desvios
  em relação à média simulada; o p-valor compara a do observado com a de cada réplica (cada uma contra a média
  das outras). H0: o observado é mais um sorteio do modelo. Não supõe distribuição.
- **atraso** (só com trajetórias): KS de duas amostras e Mann-Whitney entre os atrasos observados e os simulados
  (juntando as réplicas). A amostra observada pode excluir os veículos mais lentos (viés declarado na saída).
- **equivalência (TOST)**: só roda se você informar a tolerância (`tolerance_delay` em segundos, `tolerance_departures`
  como fração do total observado). Não há tolerância padrão: decidir quanto de diferença é aceitável é do analista.

"Não rejeitar H0" não prova que o modelo está certo: com poucos dados o teste tem pouco poder. A equivalência
é o teste que pode afirmar que a diferença cabe na tolerância.

Dados ausentes ficam de fora da comparação (e são contados). Filas marcadas como parcialmente
visíveis (`queue_visible = não`) também ficam de fora.
"""

import math
from dataclasses import replace

import numpy as np
from scipy import stats

from app.domain.validation.errors import QueueValidationError
from app.traffic.engine import simulate_replication
from app.traffic.gof import MIN_REPLICATIONS, holm, ks_and_mann_whitney, monte_carlo_bias, monte_carlo_gof, tost
from app.traffic.metrics import queue_at
from app.traffic.plan import APPROACH_KEYS, MAX_TRAFFIC_EXPECTED_ARRIVALS, ArrivalProfile, Intersection
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


def observed_profile(session: Session, approach: str, class_names: tuple[str, ...] = ()) -> ArrivalProfile:
    """O perfil de chegadas da sessão: um bloco por intervalo de contagem, com o nº observado de chegadas."""
    items = session.counts[approach]
    class_counts = None
    if class_names:
        lowered = [c.lower() for c in class_names]
        unknown = [c for c in lowered if c not in session.classes]
        if unknown:
            raise QueueValidationError(
                "As classes do cruzamento não existem nas contagens do vídeo: " + ", ".join(unknown)
                + (f". Classes do vídeo: {', '.join(session.classes)}." if session.classes else ". As contagens não têm vehicle_class."),
                "approaches")
        class_counts = tuple(tuple(int(d["by_class"][c]) if c in d["by_class"] else 0 for c in lowered) for d in items) if session.classes else None
        if class_counts is not None:
            for row, d in zip(class_counts, items):
                if sum(row) != d["arrivals"]:
                    raise QueueValidationError(
                        f"As classes do cruzamento não cobrem todas as classes do vídeo ({', '.join(session.classes)}): "
                        "as chegadas por classe não somam as chegadas do intervalo.", "approaches")
    return ArrivalProfile(
        tuple(d["start"] for d in items), tuple(d["arrivals"] / (d["end"] - d["start"]) for d in items),
        items[-1]["end"], counts=tuple(d["arrivals"] for d in items), class_counts=class_counts)


def with_observed_counts(session: Session, inter: Intersection) -> Intersection:
    """Troca o perfil de chegadas de cada aproximação pelas contagens observadas (número fixo por intervalo)."""
    if len(inter.approaches) != len(session.approach_ids):
        raise QueueValidationError(
            f"O cruzamento tem {len(inter.approaches)} aproximações e o vídeo, {len(session.approach_ids)}.", "approaches")
    approaches = [replace(app, profile=observed_profile(session, a, tuple(c.name for c in app.classes)))
                  for app, a in zip(inter.approaches, session.approach_ids)]
    return replace(inter, approaches=tuple(approaches))


MC_REPLICATIONS = 199      # p mínimo de Monte Carlo = 1/200 = 0,005; com Holm entre até 6 testes ainda dá para rejeitar (α/6 ≈ 0,008)


def boost_replications(settings: Settings, inter: Intersection) -> Settings:
    """Sobe as réplicas para MC_REPLICATIONS (além do teto de 100 do restante do sistema), se o tamanho do trabalho deixar.

    O p-valor de Monte Carlo só vai até 1 / (R + 1) e o ajuste de Holm o multiplica pelo nº de testes: com poucas
    réplicas nenhum teste conseguiria rejeitar, nem um modelo claramente errado. As réplicas a mais só aumentam a
    precisão da faixa simulada e dos testes; `settings.replications` do resultado diz quantas rodaram."""
    if settings.replications >= MC_REPLICATIONS:
        return settings
    expected = sum(a.profile.expected_arrivals(settings.simulation_time) + a.initial_queue for a in inter.approaches)
    if expected * MC_REPLICATIONS > MAX_TRAFFIC_EXPECTED_ARRIVALS:
        return settings
    return replace(settings, replications=MC_REPLICATIONS)


def _decision(p: float | None, alpha: float, equivalence: bool = False) -> str:
    if p is None:
        return "not_evaluated"
    if equivalence:
        return "equivalent" if p < alpha else "not_shown"
    return "rejected" if p < alpha else "not_rejected"


def _test(test_id: str, name: str, h0: str, p: float | None, alpha: float, statistic=None, note: str | None = None, **extra) -> dict:
    return {"id": test_id, "name": name, "h0": h0, "statistic": _finite(statistic), "p_value": _finite(p),
            "p_adjusted": None, "alpha": alpha, "decision": _decision(p, alpha, extra.get("kind") == "equivalence"),
            "note": note, **extra}


def validate_session(
    session: Session, inter: Intersection, settings: Settings, *,
    tolerance_delay: float | None = None, tolerance_departures: float | None = None,
) -> dict:
    """`inter` fornece o plano e os parâmetros de descarga; as chegadas vêm sempre das contagens observadas.

    `tolerance_delay` (s) e `tolerance_departures` (fração do total observado) são as margens do teste de
    equivalência; sem elas o TOST não roda."""
    for name, value in (("tolerance_delay", tolerance_delay), ("tolerance_departures", tolerance_departures)):
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0):
            raise QueueValidationError(f"{name} deve ser um número maior que zero.", name)
    inter = with_observed_counts(session, inter)
    T, reps = settings.simulation_time, settings.replications
    runs = [simulate_replication(inter, T, settings.seed, r) for r in range(reps)]
    level = settings.confidence_level
    alpha = 1 - level
    out = {"approaches": {}, "settings": {
        "simulation_time": T, "replications": reps, "seed": settings.seed, "band_level": level, "alpha": alpha,
        "tolerance_delay": tolerance_delay, "tolerance_departures": tolerance_departures,
        "classes": list(session.classes),
        "note": ("A faixa é o intervalo central de {:.0%} dos valores simulados entre réplicas (variação do próprio "
                 "processo), não um IC da média. Não há limite de aprovação. Os testes de `tests` usam alpha = {:.2g}; \"não rejeitado\" "
                 "não prova que o modelo está certo (pode faltar poder), e só a equivalência afirma que a diferença cabe na tolerância.").format(level, alpha),
    }, "notes": []}
    if reps < MIN_REPLICATIONS:
        out["notes"].append(f"Com menos de {MIN_REPLICATIONS} réplicas o teste de aderência (Monte Carlo) não roda: use mais réplicas.")
    elif reps < MC_REPLICATIONS:
        out["notes"].append(
            f"Com {reps} réplicas o menor p-valor de Monte Carlo é {1 / (reps + 1):.3f}; com o ajuste de Holm, testes de aderência "
            f"dificilmente rejeitam. Use ao menos {MC_REPLICATIONS} réplicas para dar poder aos testes.")

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

        tests: list[dict] = []
        gof_q = monte_carlo_gof(q_obs[q_ok], q_sim[:, q_ok])
        tests.append(_test("gof_queue", "Aderência da fila por intervalo (Monte Carlo)",
                           "o observado é mais um sorteio do modelo", gof_q and gof_q["p_value"], alpha, gof_q and gof_q["statistic"],
                           None if gof_q else "Sem intervalos de fila utilizáveis ou réplicas insuficientes."))
        bias_q = monte_carlo_bias(q_obs[q_ok], q_sim[:, q_ok])
        tests.append(_test("bias_queue", "Viés da fila por intervalo (Monte Carlo)", "a fila observada não é sistematicamente maior nem menor",
                           bias_q and bias_q["p_value"], alpha, bias_q and bias_q["statistic"],
                           "Estatística: desvio médio observado − simulado, em veículos." if bias_q else "Sem intervalos de fila utilizáveis ou réplicas insuficientes."))
        gof_d = monte_carlo_gof(d_obs[d_ok], dep_sim[:, d_ok])
        tests.append(_test("gof_departures", "Aderência das saídas por intervalo (Monte Carlo)",
                           "o observado é mais um sorteio do modelo", gof_d and gof_d["p_value"], alpha, gof_d and gof_d["statistic"],
                           None if gof_d else "Sem contagem de saídas utilizável ou réplicas insuficientes."))

        bias_d = monte_carlo_bias(d_obs[d_ok], dep_sim[:, d_ok])
        tests.append(_test("bias_departures", "Viés das saídas por intervalo (Monte Carlo)", "as saídas observadas não são sistematicamente maiores nem menores",
                           bias_d and bias_d["p_value"], alpha, bias_d and bias_d["statistic"],
                           "Estatística: desvio médio observado − simulado, em veículos por intervalo." if bias_d else "Sem contagem de saídas utilizável ou réplicas insuficientes."))
        waits = None
        if session.tracks is not None and session.tracks.get(a):
            waits = np.array([c - q for q, c, ok in session.tracks[a] if ok and c >= q], float)
            if len(waits) >= 2:
                half = stats.t.ppf((1 + level) / 2, len(waits) - 1) * waits.std(ddof=1) / math.sqrt(len(waits))
                sim_delays, pooled = [], []
                for run in runs:
                    arr, dep = run[i].arrivals[run[i].n_initial:], run[i].departures[run[i].n_initial:]
                    done = dep < T
                    sim_delays.append(float((dep[done] - arr[done]).mean()) if done.any() else math.nan)
                    pooled.append(dep[done] - arr[done])
                sim = np.array(sim_delays)
                sim = sim[~np.isnan(sim)]
                pooled_all = np.concatenate(pooled) if pooled else np.empty(0)
                entry["delay"] = {
                    "observed_mean": float(waits.mean()), "observed_ci": [float(waits.mean() - half), float(waits.mean() + half)],
                    "observed_n": int(len(waits)), "simulated_mean": float(sim.mean()),
                    "simulated_low": float(np.percentile(sim, (1 - level) / 2 * 100)),
                    "simulated_high": float(np.percentile(sim, (1 + level) / 2 * 100)),
                    "note": "O observado vem só dos veículos acompanhados até o fim (amostra que pode excluir os mais lentos).",
                }
                two = ks_and_mann_whitney(waits, pooled_all)
                bias = "A amostra observada pode excluir os veículos mais lentos, o que favorece diferenças aparentes."
                tests.append(_test("ks_delay", "Atraso: Kolmogorov–Smirnov (distribuição inteira)", "as distribuições do atraso são iguais",
                                   two and two["ks"]["p_value"], alpha, two and two["ks"]["statistic"],
                                   bias if two else "Poucos atrasos observados ou simulados."))
                tests.append(_test("mw_delay", "Atraso: Mann–Whitney (posição das distribuições)", "as distribuições do atraso são iguais",
                                   two and two["mann_whitney"]["p_value"], alpha, two and two["mann_whitney"]["statistic"],
                                   bias if two else "Poucos atrasos observados ou simulados."))
                if tolerance_delay is not None and len(waits) >= 2 and len(sim) >= 2:
                    se = math.sqrt(waits.var(ddof=1) / len(waits) + sim.var(ddof=1) / len(sim))
                    df = max(1.0, min(len(waits), len(sim)) - 1)
                    r = tost(float(waits.mean() - sim.mean()), se, float(tolerance_delay), alpha, df)
                    tests.append(_test("tost_delay", f"Equivalência do atraso médio (±{tolerance_delay:g} s)", "a diferença é maior que a tolerância",
                                       r and r["p_value"], alpha, r and r["difference"],
                                       "Equivalente: a diferença entre o atraso observado e o simulado cabe na tolerância." if r and r["equivalent"]
                                       else "Não ficou demonstrado que a diferença cabe na tolerância.", kind="equivalence",
                                       equivalent=r["equivalent"] if r else None))
        if tolerance_delay is None and waits is not None:
            tests.append(_test("tost_delay", "Equivalência do atraso médio", "a diferença é maior que a tolerância", None, alpha,
                               note="Informe tolerance_delay (s) para testar a equivalência.", kind="equivalence", equivalent=None))
        if tolerance_departures is not None and total_obs and reps >= 2:
            sd = float(total_sim.std(ddof=1))
            r = tost(float(total_sim.mean() - total_obs), sd * math.sqrt(1 + 1 / reps), tolerance_departures * total_obs, alpha, reps - 1)
            tests.append(_test("tost_departures", f"Equivalência do total de saídas (±{tolerance_departures:.1%})",
                               "a diferença é maior que a tolerância", r and r["p_value"], alpha, r and r["difference"],
                               "Equivalente: o total simulado difere do observado menos que a tolerância." if r and r["equivalent"]
                               else "Não ficou demonstrado que a diferença cabe na tolerância.", kind="equivalence",
                               equivalent=r["equivalent"] if r else None))
        elif tolerance_departures is None:
            tests.append(_test("tost_departures", "Equivalência do total de saídas", "a diferença é maior que a tolerância", None, alpha,
                               note="Informe tolerance_departures (fração do total observado) para testar a equivalência.",
                               kind="equivalence", equivalent=None))
        # Holm entre os testes de aderência/igualdade da aproximação
        family = [t for t in tests if t.get("kind") != "equivalence" and t["p_value"] is not None]
        for t, adj in zip(family, holm([t["p_value"] for t in family])):
            t["p_adjusted"] = adj
            t["decision"] = "rejected" if adj < alpha else "not_rejected"
        entry["tests"] = tests
        out["approaches"][key] = entry
    return out
