"""Comparação de planos semafóricos e varredura da divisão do verde (Fase 13.1).

Todos os planos usam as mesmas sementes e os mesmos fluxos de chegada e de intervalo de descarga
(números aleatórios comuns, ver `engine`): na réplica i, a diferença d_i = X_plano,i − X_base,i
tem variância menor do que a de duas simulações independentes. O IC da diferença é um IC t de
Student com R − 1 graus de liberdade sobre os d_i. Veredito: "higher"/"lower" quando o IC exclui 0
e "inconclusive" quando contém 0 (não significa igual: as réplicas feitas não bastam para distinguir).

Os ICs são individuais; a correção de Bonferroni (opcional) divide α pelo número de planos.
O módulo não depende da API: `prepare_*` valida tudo e `iter_*` gera os eventos na ordem em que
ficam prontos (start → um por plano/ponto → done, ou error).
"""

import math
import secrets
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import numpy as np

from app.domain.validation.errors import InsufficientSampleError, QueueValidationError
from app.simulation.stats import summarize
from app.traffic.analytic import reference
from app.traffic.metrics import APPROACH_METRICS, INTERSECTION_METRICS
from app.traffic.plan import (
    APPROACH_KEYS, MAX_TRAFFIC_EXPECTED_ARRIVALS, Intersection, Phase, Signal, alerts_of,
    build_intersection, pt,
)
from app.traffic.run import RunResult, Settings, prepare_settings, run_plan

MAX_PLANS = 10
MAX_SWEEP_POINTS = 40
HIGHER, LOWER, INCONCLUSIVE = "higher", "lower", "inconclusive"
STATUS_OK, STATUS_ERROR = "ok", "error"

# O sentido "melhor" de cada métrica: usado só para colorir na interface.
BETTER = {
    "delay": "lower", "delay_censored": "lower", "queue_mean": "lower", "queue_max": "lower",
    "queue_end": "lower", "throughput": "higher", "stopped_fraction": "lower",
    "overflow_cycles": "lower", "pending": "lower", "departures": "higher",
}
COMPARED_APPROACH = tuple(m for m in APPROACH_METRICS if m != "arrivals")
COMPARED_INTERSECTION = tuple(m for m in INTERSECTION_METRICS if m != "arrivals")


def verdict_of(ci_low: float, ci_high: float) -> str:
    if ci_low > 0:
        return HIGHER
    if ci_high < 0:
        return LOWER
    return INCONCLUSIVE


def _finite(value: object) -> object:
    """Escalares do NumPy viram nativos; NaN e infinito não existem em JSON e viram None."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def _ratio(num: float, den: float) -> float | None:
    return num / den if den not in (0, 0.0) else None


# ---------- planos ----------

@dataclass(frozen=True)
class PlanSpec:
    """Um plano alternativo: a base com algumas durações trocadas (segundos, valores absolutos)."""

    name: str | None
    phases: tuple[dict | None, dict | None]     # por fase: green / amber / all_red a trocar


def apply_plan(base: Intersection, spec: PlanSpec, index: int) -> Intersection:
    if not isinstance(spec.phases, (tuple, list)) or len(spec.phases) != 2:
        raise QueueValidationError("phases do plano deve ter 2 itens (use null para manter a fase).", f"scenarios.{index}.phases")
    built = []
    for i, change in enumerate(spec.phases):
        phase = base.signal.phases[i]
        values = {"green": phase.green, "amber": phase.amber, "all_red": phase.all_red}
        for key, value in (change or {}).items():
            values[key] = value
        label = f"scenarios.{index}.phases.{i}"
        from app.traffic.plan import build_phase
        built.append(build_phase(label, values))
    cycle = built[0].total + built[1].total
    from app.traffic.plan import MAX_CYCLE
    if cycle > MAX_CYCLE:
        raise QueueValidationError(f"O ciclo do plano ({cycle:g} s) passa do limite de {MAX_CYCLE:g} s.", f"scenarios.{index}.phases")
    if base.signal.offset >= cycle:
        raise QueueValidationError(
            f"O ciclo do plano ({cycle:g} s) é menor que o offset ({base.signal.offset:g} s).", f"scenarios.{index}.phases")
    signal = Signal((built[0], built[1]), base.signal.offset, base.signal.offset_informed)
    try:
        return build_intersection(signal, base.approaches)
    except QueueValidationError as error:
        raise QueueValidationError(str(error), f"scenarios.{index}.phases") from error


def _phases_dict(inter: Intersection) -> list[dict]:
    return [{"green": p.green, "amber": p.amber, "all_red": p.all_red} for p in inter.signal.phases]


# ---------- IC pareado ----------

def paired(new: np.ndarray, base: np.ndarray, level: float) -> dict | None:
    mask = ~(np.isnan(new) | np.isnan(base))
    if mask.sum() < 2:
        return None
    s = summarize((new[mask] - base[mask]).tolist(), level)
    return {"summary": asdict(s), "verdict": verdict_of(s.ci_low, s.ci_high)}


def _metric_block(result: RunResult, base: RunResult | None, key: str, names: tuple[str, ...], level: float) -> dict:
    block = {}
    for name in names:
        summary = (result.intersection if key == "x" else result.approaches[key])[name]
        entry = {"simulation": asdict(summary) if summary else None, "better": BETTER.get(name),
                 "diff": None, "relative_change": None, "verdict": None}
        if base is not None and summary is not None:
            base_summary = (base.intersection if key == "x" else base.approaches[key])[name]
            comparison = paired(result.raw[f"{key}.{name}"], base.raw[f"{key}.{name}"], level)
            if comparison is not None and base_summary is not None:
                entry["diff"] = comparison["summary"]
                entry["relative_change"] = _ratio(comparison["summary"]["mean"], base_summary.mean)
                entry["verdict"] = comparison["verdict"]
        block[name] = entry
    return block


def _row(index: int, name: str, inter: Intersection, settings: Settings, result: RunResult | None,
         base: RunResult | None, base_inter: Intersection, level: float, message: str | None = None) -> dict:
    alerts = alerts_of(inter, settings.simulation_time)
    if index > 0 and abs(inter.signal.cycle - base_inter.signal.cycle) > 1e-9:
        alerts.append({
            "code": "cycle_changed", "level": "info", "approach": None,
            "message": f"O ciclo mudou de {base_inter.signal.cycle:g} s para {inter.signal.cycle:g} s: a diferença mistura "
                       "redistribuição do verde e mudança da capacidade total. Para isolar a redistribuição, mantenha o ciclo.",
        })
    row = {
        "index": index, "role": "base" if index == 0 else "plan", "name": name,
        "status": STATUS_OK if result is not None else STATUS_ERROR, "message": message,
        "phases": _phases_dict(inter), "cycle": inter.signal.cycle,
        "saturation": {k: inter.saturation(i, settings.simulation_time) for i, k in enumerate(APPROACH_KEYS)},
        "alerts": alerts, "reference": reference(inter, settings.simulation_time), "metrics": {},
    }
    if result is not None:
        row["metrics"] = {
            "x": _metric_block(result, base, "x", COMPARED_INTERSECTION, level),
            **{k: _metric_block(result, base, k, COMPARED_APPROACH, level) for k in APPROACH_KEYS},
        }
    return _finite(row)


# ---------- comparação ----------

@dataclass(frozen=True)
class ComparePlan:
    base: Intersection
    plans: tuple[tuple[str, Intersection], ...]
    settings: Settings
    comparisons: int
    diff_level: float
    bonferroni: bool


def prepare_compare(
    base: Intersection, specs: list[PlanSpec], *, simulation_time: object, replications: object = 10,
    warmup_time: object = 0.0, seed: object = None, confidence_level: object = 0.95,
    bonferroni: bool = False, series_step: object = None,
) -> ComparePlan:
    if not isinstance(specs, (list, tuple)) or not 1 <= len(specs) <= MAX_PLANS:
        raise QueueValidationError(f"scenarios deve ter de 1 a {MAX_PLANS} planos (além da base).", "scenarios")
    plans = []
    for i, spec in enumerate(specs):
        name = (spec.name or f"Plano {i + 1}").strip()[:60] or f"Plano {i + 1}"
        plans.append((name, apply_plan(base, spec, i)))
    settings = prepare_settings(
        base, simulation_time=simulation_time, replications=replications, warmup_time=warmup_time,
        seed=seed, confidence_level=confidence_level, series_step=series_step, plans=1 + len(plans))
    n = len(plans)
    level = settings.confidence_level
    diff_level = 1 - (1 - level) / n if bonferroni and n > 1 else level
    return ComparePlan(base, tuple(plans), settings, n, diff_level, bool(bonferroni))


def settings_dict(s: Settings, **extra) -> dict:
    return {
        "simulation_time": s.simulation_time, "warmup_time": s.warmup_time, "replications": s.replications,
        "seed": s.seed, "confidence_level": s.confidence_level, "series_step": s.series_step, **extra,
    }


def _note(plan: ComparePlan) -> dict:
    m = plan.comparisons
    if plan.bonferroni and m > 1:
        text = (f"Correção de Bonferroni: cada IC da diferença usa nível {plan.diff_level:.4g} "
                f"(α = {1 - plan.settings.confidence_level:.3g} dividido entre {m} planos).")
    elif m > 1:
        text = (f"ICs individuais: cada intervalo tem confiança de {plan.settings.confidence_level:.0%} sozinho. "
                f"Com {m} planos e várias métricas, a chance de algum IC excluir 0 por acaso é maior do que a nominal.")
    else:
        text = "Um único plano comparado: o IC da diferença tem a confiança nominal."
    return {"correction": "bonferroni" if plan.bonferroni and m > 1 else "none", "comparisons": m,
            "confidence_level": plan.diff_level, "note": text}


def iter_compare(plan: ComparePlan) -> Iterator[dict]:
    """start → base → um "plan" por plano → done. Erro na base encerra com "error"; em um plano vira status "error"."""
    s = plan.settings
    total = 1 + len(plan.plans)
    yield {"type": "start", "total": total, "settings": settings_dict(s, diff_confidence_level=plan.diff_level),
           "multiple_comparison": _note(plan)}
    try:
        base_result = run_plan(plan.base, s)
    except InsufficientSampleError as error:
        yield {"type": "error", "code": "insufficient_sample", "message": str(error), "field": "simulation_time"}
        return
    base_row = _row(0, "Referência", plan.base, s, base_result, None, plan.base, plan.diff_level)
    base_row["series"] = _finite(base_result.series)
    yield {"type": "base", "completed": 1, "total": total, "plan": base_row}

    rows = []
    for i, (name, inter) in enumerate(plan.plans, start=1):
        try:
            result = run_plan(inter, s)
        except InsufficientSampleError as error:
            row = _row(i, name, inter, s, None, None, plan.base, plan.diff_level, str(error))
        else:
            row = _row(i, name, inter, s, result, base_result, plan.base, plan.diff_level)
            row["series"] = _finite(result.series)
        rows.append(row)
        yield {"type": "plan", "completed": i + 1, "total": total, "plan": row}
    yield {"type": "done", "result": {
        "settings": settings_dict(s, diff_confidence_level=plan.diff_level),
        "multiple_comparison": _note(plan), "base": base_row, "plans": rows}}


# ---------- varredura da divisão do verde ----------

@dataclass(frozen=True)
class SweepPlan:
    base: Intersection
    greens: tuple[tuple[float, float], ...]     # (verde 1, verde 2) de cada ponto, com o ciclo fixo
    settings: Settings
    green_total: float


def prepare_sweep(
    base: Intersection, *, min_green: object, step: object, simulation_time: object, replications: object = 10,
    warmup_time: object = 0.0, seed: object = None, confidence_level: object = 0.95,
) -> SweepPlan:
    """Mantém o ciclo e redistribui o verde: g1 + g2 = verde total da base; amarelo e todo-vermelho não mudam."""
    from app.traffic.plan import _real
    if not isinstance(min_green, (list, tuple)) or len(min_green) != 2:
        raise QueueValidationError("min_green deve ter 2 valores (verde mínimo de cada fase, em segundos).", "min_green")
    g_min = [_real(f"min_green.{i}", v, positive=True) for i, v in enumerate(min_green)]
    st = _real("step", step, positive=True)
    total = base.signal.phases[0].green + base.signal.phases[1].green
    if g_min[0] + g_min[1] > total + 1e-9:
        raise QueueValidationError(
            f"A soma dos verdes mínimos ({g_min[0] + g_min[1]:g} s) passa do verde total do ciclo ({total:g} s).", "min_green")
    count = int(math.floor((total - g_min[0] - g_min[1]) / st + 1e-9)) + 1
    if count > MAX_SWEEP_POINTS:
        raise QueueValidationError(
            f"A varredura teria {count} pontos (limite {MAX_SWEEP_POINTS}). Aumente step.", "step")
    greens = []
    for j in range(count):
        g1 = g_min[0] + j * st
        g2 = total - g1
        candidate = _with_greens(base, g1, g2)
        try:
            build_intersection(candidate.signal, candidate.approaches)
        except QueueValidationError:
            continue          # o verde efetivo ficaria ≤ 0: o ponto não existe
        greens.append((g1, g2))
    if not greens:
        raise QueueValidationError("Nenhum ponto da varredura tem verde efetivo positivo.", "min_green")
    settings = prepare_settings(
        base, simulation_time=simulation_time, replications=replications, warmup_time=warmup_time, seed=seed,
        confidence_level=confidence_level, plans=len(greens))
    return SweepPlan(base, tuple(greens), settings, total)


def _with_greens(base: Intersection, g1: float, g2: float) -> Intersection:
    p1, p2 = base.signal.phases
    signal = Signal((Phase(g1, p1.amber, p1.all_red), Phase(g2, p2.amber, p2.all_red)),
                    base.signal.offset, base.signal.offset_informed)
    return Intersection(signal, base.approaches)


def iter_sweep(plan: SweepPlan) -> Iterator[dict]:
    s = plan.settings
    total = len(plan.greens)
    yield {"type": "start", "total": total, "cycle": plan.base.signal.cycle, "green_total": plan.green_total,
           "settings": settings_dict(s)}
    points, results = [], []
    for j, (g1, g2) in enumerate(plan.greens):
        inter = _with_greens(plan.base, g1, g2)
        try:
            result = run_plan(inter, s, with_series=False)
        except InsufficientSampleError as error:
            yield {"type": "error", "code": "insufficient_sample", "message": str(error), "field": "simulation_time"}
            return
        results.append(result)
        point = {
            "index": j, "green": [g1, g2],
            "saturation": {k: inter.saturation(i, s.simulation_time) for i, k in enumerate(APPROACH_KEYS)},
            "intersection": {m: asdict(v) if v else None for m, v in result.intersection.items()},
            "a1": {m: asdict(v) if v else None for m, v in result.approaches["a1"].items()},
            "a2": {m: asdict(v) if v else None for m, v in result.approaches["a2"].items()},
            "reference_delay": reference(inter, s.simulation_time)["delay_censored"],
        }
        point = _finite(point)
        points.append(point)
        yield {"type": "point", "completed": j + 1, "total": total, "point": point}

    # melhor ponto = menor atraso médio do cruzamento (com pendentes), e quem não se distingue dele
    means = [p["intersection"]["delay_censored"]["mean"] if p["intersection"]["delay_censored"] else math.inf for p in points]
    best = int(np.argmin(means))
    level = s.confidence_level
    for j, (point, result) in enumerate(zip(points, results)):
        if j == best:
            point["vs_best"] = {"verdict": "best", "diff": None}
            continue
        comparison = paired(result.raw["x.delay_censored"], results[best].raw["x.delay_censored"], level)
        point["vs_best"] = (
            {"verdict": "worse" if comparison["verdict"] == HIGHER else "indistinguishable" if comparison["verdict"] == INCONCLUSIVE else "better",
             "diff": _finite(comparison["summary"])}
            if comparison else {"verdict": "unknown", "diff": None})
    yield {"type": "done", "result": {
        "settings": settings_dict(s), "cycle": plan.base.signal.cycle, "green_total": plan.green_total,
        "best_index": best, "points": points,
        "webster_cycle": reference(plan.base, s.simulation_time)["webster_cycle"],
        "note": ("O melhor ponto é o de menor atraso médio com pendentes. \"indistinguishable\" significa que o IC pareado da "
                 "diferença para o melhor contém 0 com as réplicas feitas: não há evidência de que sejam diferentes."),
    }}


def run_compare(plan: ComparePlan) -> dict:
    result = None
    for event in iter_compare(plan):
        if event["type"] == "error":
            raise InsufficientSampleError(event["message"], field=event.get("field"))
        if event["type"] == "done":
            result = event["result"]
    assert result is not None
    return result


def run_sweep(plan: SweepPlan) -> dict:
    result = None
    for event in iter_sweep(plan):
        if event["type"] == "error":
            raise InsufficientSampleError(event["message"], field=event.get("field"))
        if event["type"] == "done":
            result = event["result"]
    assert result is not None
    return result
