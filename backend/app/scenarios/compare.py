"""Comparação de cenários com intervalo de confiança pareado (Fase 12, Etapa 1).

A base e os cenários são simulados com R réplicas cada, com as mesmas sementes e fluxos
separados de chegada e serviço (números aleatórios comuns, ver `engine`). Na réplica i, a
diferença d_i = X_cenário,i − X_base,i tem variância menor do que a de duas simulações
independentes, porque as duas réplicas enfrentam as mesmas chegadas e os mesmos serviços. O IC
da diferença é um IC t de Student com R − 1 graus de liberdade sobre os d_i.

Veredito por métrica: "higher"/"lower" quando o IC da diferença exclui 0 (com o sentido), e
"inconclusive" quando o IC contém 0. Inconclusivo não significa igual: significa que as
réplicas feitas não bastam para distinguir. Os ICs são individuais; a correção de Bonferroni
(opcional) divide α pelo número de cenários comparados.

Este módulo não depende da API: `prepare` valida e resolve tudo; `iter_comparison` gera os
eventos (base, cada cenário, resultado final) na ordem em que ficam prontos.
"""

import math
import secrets
from collections.abc import Iterator
from dataclasses import asdict, dataclass

import numpy as np

from app.analytical.mgc import is_exact, validity_warnings
from app.domain.validation.errors import (
    InsufficientSampleError, QueueValidationError, UnstableSystemError,
)
from app.domain.validation.experiments import MAX_SWEEP_EXPECTED_ARRIVALS
from app.domain.validation.simulation import validate_simulation_settings
from app.experiments.general import general_experiment_metrics
from app.experiments.points import analytical_metrics
from app.scenarios.engine import simulate_runs, summarize_runs
from app.scenarios.spec import (
    INFINITE_QUEUE_MODELS, MAX_SCENARIOS, BaseSpec, Resolved, ScenarioSpec,
    changes, resolve_base, resolve_scenario,
)
from app.simulation.results import QUEUE_METRIC_NAMES
from app.simulation.stats import summarize

# Teto de trabalho: o mesmo dos experimentos, somado entre a base e os cenários simulados.
MAX_EXPECTED_ARRIVALS = MAX_SWEEP_EXPECTED_ARRIVALS

STATUS_OK, STATUS_UNSTABLE, STATUS_ERROR = "ok", "unstable", "error"
HIGHER, LOWER, INCONCLUSIVE = "higher", "lower", "inconclusive"
AT_RISK_RHO = 0.9      # ρ a partir do qual o resultado de regime depende de T e do warm-up

# Métricas que cada modelo define (o analítico dos modelos que não têm P0 ou P(esperar) não os traz).
_NO_P_WAIT_NO_P_BLOCK = {"rho", "L", "Lq", "W", "Wq", "p0", "throughput"}          # M/M/1 e M/G/1
_MGC = {"rho", "L", "Lq", "W", "Wq", "throughput", "p_wait"}                        # M/G/c: sem P0
_METRICS_OF = {"mm1": _NO_P_WAIT_NO_P_BLOCK, "mg1": _NO_P_WAIT_NO_P_BLOCK, "mgc": _MGC}


def metric_names(model: str) -> tuple[str, ...]:
    """Métricas definidas no modelo, na ordem canônica (as que não existem aparecem como "—")."""
    allowed = _METRICS_OF.get(model)
    return tuple(name for name in QUEUE_METRIC_NAMES if allowed is None or name in allowed)


# ---------- analítico e alertas ----------

@dataclass(frozen=True)
class Analytic:
    status: str                         # "ok" | "unstable"
    message: str | None
    metrics: dict[str, float] | None
    exact: bool


def analytic_of(scenario: Resolved) -> Analytic:
    """Métricas analíticas do cenário; ρ ≥ 1 (fila ilimitada) vira status "unstable"."""
    try:
        if scenario.general_service:
            metrics = general_experiment_metrics(
                scenario.model, scenario.lam, scenario.service, scenario.servers)
            exact = scenario.model == "mg1" or is_exact(scenario.service, scenario.servers)
        else:
            mu = float(f"{scenario.service.mu:.12g}")   # sem o ruído de 1/(1/μ) na borda ρ = 1
            metrics = analytical_metrics(
                scenario.model, scenario.lam, mu, scenario.servers, scenario.capacity)
            exact = True
    except UnstableSystemError as error:
        return Analytic(STATUS_UNSTABLE, str(error), None, False)
    wanted = metric_names(scenario.model)
    return Analytic(STATUS_OK, None, {name: float(metrics[name]) for name in wanted}, exact)


def alerts_of(scenario: Resolved, analytic: Analytic) -> list[dict]:
    """Instável (erro), em risco (aviso) e faixa de validade da aproximação do M/G/c (aviso)."""
    rho = scenario.offered_utilization
    out: list[dict] = []
    if analytic.status == STATUS_UNSTABLE:
        out.append({
            "code": "unstable", "level": "error",
            "message": (f"ρ = {rho:.4g} ≥ 1: com fila ilimitada o sistema não atinge regime estacionário. "
                        "O cenário não foi simulado e não tem valores analíticos."),
        })
    elif scenario.model in INFINITE_QUEUE_MODELS and rho >= AT_RISK_RHO:
        out.append({
            "code": "at_risk", "level": "warning",
            "message": (f"ρ = {rho:.4g} ≥ {AT_RISK_RHO:g}: perto da saturação, a simulação converge devagar e "
                        "a diferença para o analítico depende de simulation_time e do warm-up."),
        })
    if scenario.model == "mgc" and analytic.status == STATUS_OK:
        for message in validity_warnings(rho, scenario.service.cv, scenario.servers):
            out.append({"code": "approximation", "level": "warning", "message": message})
    return out


# ---------- preparo (validação e resolução) ----------

@dataclass(frozen=True)
class Settings:
    simulation_time: float
    warmup_time: float
    replications: int
    seed: int
    confidence_level: float
    bonferroni: bool


@dataclass(frozen=True)
class Plan:
    base: Resolved
    scenarios: tuple[Resolved, ...]
    settings: Settings
    analytics: tuple[Analytic, ...]     # base primeiro, depois um por cenário
    comparisons: int                    # cenários que serão simulados e comparados com a base
    diff_level: float                   # nível dos ICs da diferença (com Bonferroni, 1 − α/m)
    expected_arrivals: float            # Σ λ·T·R entre a base e os cenários simulados

    @property
    def total(self) -> int:
        return 1 + len(self.scenarios)

    def simulated(self, index: int) -> bool:
        return index == 0 or self.analytics[index].status == STATUS_OK


def _pt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def prepare(
    base: BaseSpec,
    scenarios: list[ScenarioSpec],
    *,
    simulation_time: object,
    replications: object = 10,
    warmup_time: object = 0.0,
    seed: object = None,
    confidence_level: object = 0.95,
    bonferroni: bool = False,
) -> Plan:
    """Valida o pedido inteiro antes de simular qualquer coisa (erros 422 com o campo).

    A base precisa ser estável. Cenário instável não é um erro: sai com o aviso e só o analítico
    (que, sendo instável, não existe) e não entra na conta do trabalho.
    """
    if not isinstance(scenarios, (list, tuple)) or not 1 <= len(scenarios) <= MAX_SCENARIOS:
        raise QueueValidationError(
            f"scenarios deve ter de 1 a {MAX_SCENARIOS} cenários (além da base).", "scenarios")
    base_resolved = resolve_base(base)
    resolved = tuple(resolve_scenario(base_resolved, spec, i) for i, spec in enumerate(scenarios))

    base_analytic = analytic_of(base_resolved)
    if base_analytic.status == STATUS_UNSTABLE:
        raise UnstableSystemError(
            f"A base não está em condição estável: {base_analytic.message}", field="base.lambda")
    analytics = (base_analytic, *(analytic_of(sc) for sc in resolved))
    simulated = [base_resolved, *(sc for sc, a in zip(resolved, analytics[1:]) if a.status == STATUS_OK)]

    if simulation_time is None:
        raise QueueValidationError("simulation_time é obrigatório.", "simulation_time")
    T, reps, warmup, seed_v, level = validate_simulation_settings(
        max(sc.lam for sc in simulated), simulation_time, replications, warmup_time, seed, confidence_level)
    expected = sum(sc.lam * T * reps for sc in simulated)
    if expected > MAX_EXPECTED_ARRIVALS:
        raise QueueValidationError(
            f"Comparação grande demais (~{_pt(expected)} chegadas esperadas somando a base e os cenários; "
            f"limite {_pt(MAX_EXPECTED_ARRIVALS)}). Reduza simulation_time, replications ou o número de cenários.",
            "simulation_time",
        )
    if seed_v is None:
        seed_v = secrets.randbits(32)       # pequeno o bastante para trafegar em JSON

    comparisons = len(simulated) - 1
    diff_level = 1 - (1 - level) / comparisons if bonferroni and comparisons > 1 else level
    return Plan(
        base=base_resolved, scenarios=resolved,
        settings=Settings(T, warmup, reps, seed_v, level, bool(bonferroni)),
        analytics=analytics, comparisons=comparisons, diff_level=diff_level, expected_arrivals=expected,
    )


# ---------- resultado ----------

def _finite(value: object) -> object:
    """Escalares do NumPy viram nativos; NaN e infinito não existem em JSON e viram None (o "—" da tela)."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite(v) for v in value]
    return value


def verdict_of(ci_low: float, ci_high: float) -> str:
    if ci_low > 0:
        return HIGHER
    if ci_high < 0:
        return LOWER
    return INCONCLUSIVE


def _ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator != 0 else None


def _row_header(index: int, scenario: Resolved, analytic: Analytic, plan: Plan, status: str, message: str | None) -> dict:
    return {
        "index": index,
        "role": "base" if index == 0 else "scenario",
        "name": scenario.name,
        "model": scenario.model,
        "model_label": scenario.label,
        "status": status,
        "message": message,
        "parameters": scenario.parameters(),
        "changes": [] if index == 0 else changes(plan.base, scenario),
        "alerts": alerts_of(scenario, analytic),
        "offered_utilization": scenario.offered_utilization,
        "analytic_exact": analytic.exact,
        "metrics": {},
    }


def _metric_entries(scenario: Resolved, analytic: Analytic, summary: dict | None) -> dict[str, dict]:
    entries = {}
    for name in metric_names(scenario.model):
        entries[name] = {
            "analytic": analytic.metrics.get(name) if analytic.metrics else None,
            "simulation": asdict(summary[name]) if summary else None,
            "diff": None, "relative_change": None, "verdict": None,
            "analytic_diff": None, "analytic_relative_change": None, "analytic_diff_in_ci": None,
        }
    return entries


def _add_comparison(
    entries: dict[str, dict], base_entries: dict[str, dict], runs: tuple, base_runs: tuple, diff_level: float,
) -> None:
    """IC pareado da diferença, variação relativa, veredito e diferença analítica, por métrica."""
    for name, entry in entries.items():
        base_entry = base_entries.get(name)
        if base_entry is None or entry["simulation"] is None or base_entry["simulation"] is None:
            continue                                 # a métrica não existe nos dois modelos: "—"
        diffs = [getattr(r, name) - getattr(b, name) for r, b in zip(runs, base_runs)]
        summary = summarize(diffs, diff_level)
        entry["diff"] = asdict(summary)
        entry["relative_change"] = _ratio(summary.mean, base_entry["simulation"]["mean"])
        entry["verdict"] = verdict_of(summary.ci_low, summary.ci_high)
        if entry["analytic"] is not None and base_entry["analytic"] is not None:
            analytic_diff = entry["analytic"] - base_entry["analytic"]
            entry["analytic_diff"] = analytic_diff
            entry["analytic_relative_change"] = _ratio(analytic_diff, base_entry["analytic"])
            entry["analytic_diff_in_ci"] = summary.ci_low <= analytic_diff <= summary.ci_high


def _multiple_comparison(plan: Plan) -> dict:
    m = plan.comparisons
    if plan.settings.bonferroni and m > 1:
        note = (f"Correção de Bonferroni: cada IC da diferença usa nível {plan.diff_level:.4g} "
                f"(α = {1 - plan.settings.confidence_level:.3g} dividido entre {m} cenários).")
    elif m > 1:
        note = (f"ICs individuais: cada intervalo tem confiança de {plan.settings.confidence_level:.0%} sozinho. "
                f"Com {m} cenários e várias métricas, a chance de algum IC excluir 0 por acaso é maior "
                "do que a nominal; a correção de Bonferroni deixa os intervalos mais conservadores.")
    else:
        note = "Um único cenário comparado: o IC da diferença tem a confiança nominal."
    return {
        "correction": "bonferroni" if plan.settings.bonferroni and m > 1 else "none",
        "comparisons": m,
        "confidence_level": plan.diff_level,
        "individual_intervals": m > 1 and not plan.settings.bonferroni,
        "note": note,
    }


def settings_dict(plan: Plan) -> dict:
    s = plan.settings
    return {
        "simulation_time": s.simulation_time, "warmup_time": s.warmup_time, "replications": s.replications,
        "seed": s.seed, "confidence_level": s.confidence_level, "bonferroni": s.bonferroni,
        "diff_confidence_level": plan.diff_level, "simulated_scenarios": plan.comparisons,
        "expected_arrivals": plan.expected_arrivals,
    }


def iter_comparison(plan: Plan) -> Iterator[dict]:
    """Eventos da comparação, na ordem em que ficam prontos.

    start → base → um "scenario" por cenário (na ordem do pedido) → done (com o resultado completo).
    Um erro na base (amostra insuficiente) encerra com um evento "error". Em um cenário, vira
    status "error" no próprio cenário, e os demais seguem. Quem fecha o gerador (conexão cancelada)
    interrompe o trabalho entre um cenário e outro.
    """
    s = plan.settings
    yield {"type": "start", "total": plan.total, "settings": settings_dict(plan),
           "multiple_comparison": _multiple_comparison(plan)}

    base = plan.base
    try:
        base_runs = simulate_runs(base, s.simulation_time, s.warmup_time, s.replications, s.seed)
    except InsufficientSampleError as error:
        yield {"type": "error", "code": "insufficient_sample", "message": str(error), "field": "simulation_time"}
        return
    base_analytic = plan.analytics[0]
    base_row = _row_header(0, base, base_analytic, plan, STATUS_OK, None)
    base_row["metrics"] = _metric_entries(
        base, base_analytic, summarize_runs(base_runs, metric_names(base.model), s.confidence_level))
    base_row = _finite(base_row)
    yield {"type": "base", "completed": 1, "total": plan.total, "scenario": base_row}

    rows = []
    for index, scenario in enumerate(plan.scenarios, start=1):
        analytic = plan.analytics[index]
        if analytic.status == STATUS_UNSTABLE:
            row = _row_header(index, scenario, analytic, plan, STATUS_UNSTABLE, analytic.message)
        else:
            try:
                runs = simulate_runs(scenario, s.simulation_time, s.warmup_time, s.replications, s.seed)
            except InsufficientSampleError as error:
                row = _row_header(index, scenario, analytic, plan, STATUS_ERROR, str(error))
                row["metrics"] = _metric_entries(scenario, analytic, None)
            else:
                row = _row_header(index, scenario, analytic, plan, STATUS_OK, None)
                row["metrics"] = _metric_entries(
                    scenario, analytic, summarize_runs(runs, metric_names(scenario.model), s.confidence_level))
                _add_comparison(row["metrics"], base_row["metrics"], runs, base_runs, plan.diff_level)
        row = _finite(row)
        rows.append(row)
        yield {"type": "scenario", "completed": index + 1, "total": plan.total, "scenario": row}

    yield {"type": "done", "result": {
        "settings": settings_dict(plan), "multiple_comparison": _multiple_comparison(plan),
        "base": base_row, "scenarios": rows,
    }}


def run_comparison(plan: Plan) -> dict:
    """Roda tudo e devolve o resultado completo (sem streaming). Usado pelo CSV e pelos testes."""
    result = None
    for event in iter_comparison(plan):
        if event["type"] == "error":
            raise InsufficientSampleError(event["message"], field=event.get("field"))
        if event["type"] == "done":
            result = event["result"]
    assert result is not None
    return result
