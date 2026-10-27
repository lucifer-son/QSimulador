"""Verificação dos dados e recomendação do modelo de melhor ajuste (requisito da professora).

Fluxo: janela e níveis de carga -> diagnósticos -> estimativa de parâmetros -> elegibilidade
estrutural de cada candidato -> previsão e escore (só em métricas não usadas na calibração) ->
ranking com preferência pelo modelo mais simples em empates -> confiança e justificativa.

A recomendação é o melhor ajuste **dentro do catálogo**; não prova que o sistema real seja
aquele modelo.
"""

import math
from dataclasses import asdict, dataclass, field
from typing import Callable

import numpy as np
from scipy.optimize import brentq

from app.analysis.comparison import relative_error_pct
from app.analysis.suggestion import SERVICE, suggest_from_cv
from app.analytical.finite_population import finite_population_metrics
from app.analytical.mmck import queue_metrics
from app.domain.metrics.queue_metrics import QueueModelMetrics
from app.domain.validation.errors import (
    InsufficientSampleError, InvalidDatasetError, QueueValidationError,
)
from app.domain.validation.realdata import AnalysisContext
from app.realdata import thresholds as T
from app.realdata.diagnostics import CRITICAL, Diagnostic, classify_system, diagnose, saturation
from app.realdata.estimation import Estimates, estimate
from app.realdata.jmeter import JMeterDataset
from app.realdata.metrics import (
    EmpiricalMetrics, LoadLevel, compute_metrics, response_trend, split_levels, trimmed_window,
)


# ---------- candidatos ----------

@dataclass(frozen=True)
class Candidate:
    key: str
    family: str           # open | closed
    finite_capacity: bool
    multi_server: bool
    parsimony: int        # menor = mais simples

    def notation(self, est: Estimates, levels: list[LoadLevel]) -> str:
        """Notação de Kendall. Letras (c, K, N) aparecem quando o valor ainda não é conhecido."""
        if self.multi_server:
            servers = str(est.servers) if est.servers >= 2 else "c"
        else:
            servers = "1"
        if self.family == "closed":
            users = sorted({lv.users for lv in levels if lv.users})
            return f"M/M/{servers}//{users[-1] if len(users) == 1 else 'N'}"
        base = f"M/M/{servers}"
        if self.finite_capacity:
            return f"{base}/{est.capacity if est.capacity else 'K'}"
        return base


CANDIDATES = (
    Candidate("mm1", "open", False, False, 0),
    Candidate("mmc", "open", False, True, 1),
    Candidate("mm1k", "open", True, False, 2),
    Candidate("mmck", "open", True, True, 3),
    Candidate("mm1n", "closed", False, False, 4),
    Candidate("mmcn", "closed", False, True, 5),
)


@dataclass(frozen=True)
class Rule:
    id: str
    passed: bool
    reason: str
    soft: bool = False   # regra "de capacidade/estabilidade": ignorada ao procurar o modelo mais próximo


@dataclass(frozen=True)
class Evaluation:
    key: str
    notation: str
    eligible: bool
    rules: list[Rule]
    score_pct: float | None
    scored_metrics: int
    mu_used: float | None
    reasons: list[str]
    error_pct: float | None = None     # erro relativo médio nas métricas de validação
    penalty_pp: float = 0.0            # penalidade de parcimônia (parâmetros estimados com os mesmos dados)


# ---------- previsão e escore ----------

def _servers(cand: Candidate, est: Estimates) -> int:
    return est.servers if cand.multi_server else 1


def _predict(cand: Candidate, lv: LoadLevel, est: Estimates, mu: float) -> QueueModelMetrics:
    c = _servers(cand, est)
    if cand.family == "closed":
        return finite_population_metrics(mu, c, lv.users, est.think_time)
    capacity = est.capacity if cand.finite_capacity else None
    return queue_metrics(lv.metrics.arrival_rate, mu, c, capacity)


def _calibrate_mu(cand: Candidate, lv: LoadLevel, est: Estimates) -> float | None:
    """μ tal que o tempo de resposta previsto iguala o medido (só no caso autoconsistente)."""
    target = lv.metrics.mean_response
    c = _servers(cand, est)
    lo = 1e-9 if (cand.family == "closed" or cand.finite_capacity) else lv.metrics.arrival_rate / c * (1 + 1e-9)

    def gap(mu: float) -> float:
        return _predict(cand, lv, est, mu).W - target

    try:
        hi = 1e9
        if gap(lo) <= 0 or gap(hi) >= 0:
            return None
        return float(brentq(gap, lo, hi, xtol=1e-12, rtol=1e-12, maxiter=500))
    except (QueueValidationError, ValueError, FloatingPointError):
        return None


def _errors(cand: Candidate, levels: list[LoadLevel], est: Estimates, mu: float,
            use_w: bool) -> tuple[list[float], list[str]]:
    errs: list[float] = []
    reasons: list[str] = []
    for lv in levels:
        pred = _predict(cand, lv, est, mu)
        obs = lv.metrics

        def add(model: float, observed: float) -> None:
            e = relative_error_pct(model, observed)
            errs.append(T.ERROR_CAP_PCT if e is None else min(e, T.ERROR_CAP_PCT))

        if use_w:
            add(pred.W, obs.mean_response)
        if cand.family == "closed":
            add(pred.throughput, obs.throughput)
        if cand.finite_capacity:
            add(pred.throughput, obs.throughput)
            if obs.p_block > 0:
                add(pred.p_block, obs.p_block)
        if cand.family == "open" and not cand.finite_capacity and not cand.multi_server:
            rate = mu - obs.arrival_rate
            if rate > 0:
                add(math.log(10) / rate, obs.p90)   # M/M/1: P(R > t) = e^{-(μ-λ)t}
    return errs, reasons


def _evaluate(cand: Candidate, levels: list[LoadLevel], est: Estimates, system: str,
              rej_relevant: bool) -> Evaluation:
    notation = cand.notation(est, levels)
    rules: list[Rule] = []

    if cand.family == "open":
        rules.append(Rule("estrutura", system == "open",
            "Sistema aberto: as chegadas não dependem das respostas." if system == "open"
            else "O teste é um sistema fechado (número fixo de usuários); modelos abertos não representam essa dependência."))
    else:
        rules.append(Rule("estrutura", system == "closed",
            "Sistema fechado: número fixo de usuários." if system == "closed"
            else "O teste foi classificado como aberto; modelos de população finita não se aplicam."))

    if cand.finite_capacity:
        rules.append(Rule("capacidade", rej_relevant,
            "Há rejeições relevantes: capacidade finita K é necessária." if rej_relevant
            else "Não há rejeições relevantes: capacidade finita K não se justifica.", soft=True))
    elif cand.family == "open":
        rules.append(Rule("capacidade", not rej_relevant,
            "Sem rejeições relevantes: capacidade infinita é compatível." if not rej_relevant
            else "Há rejeições relevantes: um modelo de capacidade infinita não as explica.", soft=True))
    else:
        rules.append(Rule("capacidade", not rej_relevant,
            "Sem rejeições relevantes." if not rej_relevant
            else "Há rejeições, e o catálogo não tem modelo fechado com capacidade finita.", soft=True))

    if cand.multi_server:
        ok = est.servers >= 2
        rules.append(Rule("servidores", ok,
            f"c = {est.servers} ({est.servers_source})." if ok
            else ("c = 1 com os dados disponíveis." if est.servers_source != "assumido"
                  else "c não é identificável e foi assumido 1; c ≥ 2 não foi demonstrado.")))
    else:
        ok = est.servers == 1
        rules.append(Rule("servidores", ok,
            "c = 1." if ok else f"c = {est.servers} ({est.servers_source}); este modelo tem um só servidor."))

    if cand.family == "closed":
        has = all(lv.users for lv in levels) and est.think_time is not None
        rules.append(Rule("dados", has,
            "N (usuários) e Z (tempo de reflexão) disponíveis." if has
            else "Faltam N (coluna allThreads) ou Z (tempo de reflexão) para o modelo de população finita."))

    mu = est.mu
    if mu is not None and cand.family == "open" and not cand.finite_capacity:
        bad = [lv for lv in levels if lv.metrics.arrival_rate >= _servers(cand, est) * mu]
        rules.append(Rule("estabilidade", not bad,
            "λ̂ < c·μ̂ em todos os níveis." if not bad
            else f"λ̂ = {bad[0].metrics.arrival_rate:.2f} ≥ c·μ̂ = {_servers(cand, est) * mu:.2f}: instável.".replace(".", ","),
            soft=True))

    eligible = all(r.passed for r in rules)
    reasons = [r.reason for r in rules]
    mu_used, score, scored, error, penalty = mu, None, 0, None, 0.0
    structural_ok = all(r.passed or r.soft for r in rules)
    if structural_ok:
        try:
            if mu_used is None:
                mu_used = _calibrate_mu(cand, levels[0], est)
                if mu_used is None:
                    rules.append(Rule("calibracao", False, "Não foi possível calibrar μ pelo tempo de resposta."))
                    eligible = False
            if mu_used is not None:
                errs, _ = _errors(cand, levels, est, mu_used, use_w=not est.autoconsistent)
                scored = len(errs)
                if errs:
                    extra = (est.servers_source == "estimado") + (est.capacity_source == "estimado" and cand.finite_capacity) \
                        + (cand.family == "closed" and est.think_source == "estimado") + est.autoconsistent
                    error = float(np.mean(errs))
                    penalty = T.PARAM_PENALTY_PP * extra
                    score = error + penalty
        except QueueValidationError as exc:
            rules.append(Rule("previsao", False, f"O modelo não é aplicável a estes parâmetros: {exc}"))
            eligible = False
        reasons = [r.reason for r in rules]
    return Evaluation(cand.key, notation, eligible, rules, score, scored, mu_used, reasons, error, penalty)


# ---------- resultado ----------

@dataclass(frozen=True)
class AnalysisResult:
    status: str                      # recommended | no_good_fit
    confidence: str                  # alta | media | baixa
    recommended: dict | None
    nearest: dict | None
    ranking: list[dict]
    rationale: str
    warnings: list[str]
    diagnostics: list[Diagnostic]
    system_type: str
    estimates: Estimates
    overall: EmpiricalMetrics
    levels: list[dict]
    comparison: list[dict]
    dataset: dict
    service_hint: dict | None = None   # Fase 13: sugestão M/M/c, M/D/c ou M/G/c pelo CV (não altera o ranking)

    def as_dict(self) -> dict:
        data = _jsonable(asdict(self))
        data["estimates"]["autoconsistent"] = self.estimates.autoconsistent
        return data


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (float, np.floating)):
        f = float(obj)
        return f if math.isfinite(f) else None
    return obj


def _pt(x: float, d: int = 2) -> str:
    return f"{x:.{d}f}".replace(".", ",")


def compare_to_observed(cand: Candidate, est: Estimates, mu: float, levels: list[LoadLevel]) -> list[dict]:
    """Modelo × medição por nível. Erro relativo em relação ao **observado** (fórmula do README)."""
    out = []
    for lv in levels:
        pred = _predict(cand, lv, est, mu)
        obs = lv.metrics
        rows = {"W": (pred.W, obs.mean_response, obs.summaries["W"]),
                "throughput": (pred.throughput, obs.throughput, obs.summaries["throughput"]),
                "L": (pred.L, obs.mean_in_flight, None)}
        if cand.finite_capacity:
            rows["p_block"] = (pred.p_block, obs.p_block, None)
        metrics = {}
        for name, (model, observed, summ) in rows.items():
            has_ci = summ is not None and summ.ci_low is not None
            metrics[name] = {
                "model": model, "observed": observed,
                "observed_ci_low": summ.ci_low if has_ci else None,
                "observed_ci_high": summ.ci_high if has_ci else None,
                "absolute_error": abs(model - observed),
                "relative_error_pct": relative_error_pct(model, observed),
                "model_within_observed_ci": bool(summ.ci_low <= model <= summ.ci_high) if has_ci else None,
            }
        out.append({"users": lv.users, "metrics": metrics})
    return out


def _confidence(best: Evaluation | None, second: Evaluation | None, est: Estimates,
                levels: list[LoadLevel], diags: list[Diagnostic], status: str) -> str:
    if best is None or best.score_pct is None or status == "no_good_fit":
        return "baixa"
    if est.autoconsistent or any(d.status == CRITICAL for d in diags):
        return "baixa"
    gap = (second.score_pct - best.score_pct) if second and second.score_pct is not None else float("inf")
    independent = est.mu_source in ("informado", "menor_nivel")
    if (best.score_pct < T.CONF_HIGH_SCORE and gap >= T.CONF_GAP_PP and est.servers_source != "assumido"
            and (len(levels) >= T.CONF_MIN_LEVELS or independent)):
        return "alta"
    return "media" if best.score_pct < T.CONF_MEDIUM_SCORE else "baixa"


def _rationale(system: str, rec: Evaluation | None, nearest: Evaluation | None, evals: list[Evaluation],
               est: Estimates, levels: list[LoadLevel], status: str, confidence: str, rej: float) -> str:
    parts = []
    top = levels[-1].metrics
    if system == "closed":
        parts.append(f"O teste é um sistema fechado (N̄ ≈ {_pt(top.mean_users or 0, 0)} usuários).")
    else:
        parts.append("O teste foi tratado como sistema aberto (chegadas independentes das respostas).")
    if len(levels) > 1:
        users = [lv.users for lv in levels if lv.users]
        if users:
            parts.append("Níveis de carga analisados: " + ", ".join(str(u) for u in users[:-1]) + f" e {users[-1]} usuários.")
    parts.append(f"Houve rejeições em {_pt(rej * 100)} % das requisições." if rej >= T.REJECTION_RELEVANT
                 else "Não houve rejeições relevantes.")
    chosen = rec or nearest
    if chosen is None:
        parts.append("Nenhum modelo do catálogo é compatível com a estrutura dos dados.")
    else:
        verb = "Recomendado" if status == "recommended" else "Mais próximo do catálogo (sem bom ajuste)"
        lv = levels[-1]
        text = f"{verb}: {chosen.notation}."
        if chosen.mu_used and not est.autoconsistent:
            pred = _predict(next(c for c in CANDIDATES if c.key == chosen.key), lv, est, chosen.mu_used)
            err = relative_error_pct(pred.W, lv.metrics.mean_response)
            text += (f" Tempo médio de resposta previsto {_pt(pred.W, 3)} s contra {_pt(lv.metrics.mean_response, 3)} s medido"
                     + (f" (erro de {_pt(err, 1)} %)." if err is not None else "."))
        elif est.autoconsistent:
            text += " μ foi calibrado pelo próprio tempo de resposta, então esse tempo não valida o modelo."
        parts.append(text)
    # Descartes mais informativos primeiro (capacidade, estabilidade, servidores) e sem repetir o motivo.
    seen, shown = set(), 0
    candidates = [e for e in evals if not e.eligible and e is not chosen]
    candidates.sort(key=lambda e: next((r.id for r in e.rules if not r.passed), "") == "estrutura")
    for e in candidates:
        why = next((r.reason for r in e.rules if not r.passed), "")
        if why and why not in seen and shown < 2:
            seen.add(why)
            shown += 1
            parts.append(f"{e.notation} descartado: {why}")
    parts.append(f"Confiança {confidence}. A recomendação é o melhor ajuste dentro do catálogo de modelos; "
                 "não prova que o sistema real siga esse modelo.")
    return " ".join(parts)


def analyze(ds: JMeterDataset, ctx: AnalysisContext | None = None) -> AnalysisResult:
    ctx = ctx or AnalysisContext()
    total_rows = len(ds)
    if ctx.labels:
        mask = np.isin(ds.label, list(ctx.labels))
        if not mask.any():
            raise InvalidDatasetError("Nenhuma amostra tem os rótulos (label) informados.", "labels")
        ds = ds.select(mask)

    levels = split_levels(ds, ctx.trim_start_pct, ctx.trim_end_pct, ctx.confidence_level)
    for lv in levels:
        if lv.metrics.samples < T.MIN_SAMPLES or lv.metrics.successes < T.MIN_SAMPLES:
            raise InsufficientSampleError(
                f"A janela de análise tem só {lv.metrics.successes} amostras bem-sucedidas; "
                f"são necessárias pelo menos {T.MIN_SAMPLES}.", "file")

    lo, hi = trimmed_window(ds, ctx.trim_start_pct, ctx.trim_end_pct)
    overall = levels[0].metrics if len(levels) == 1 else compute_metrics(ds, lo, hi, ctx.confidence_level)
    trends = [response_trend(ds, lv.metrics.window_start, lv.metrics.window_end) for lv in levels]

    system, system_diag = classify_system(levels, ctx)
    plateau, x_max = saturation(levels)
    est = estimate(levels, system, ctx, plateau, x_max)
    rej = max(lv.metrics.p_block for lv in levels)
    rej_relevant = rej >= T.REJECTION_RELEVANT
    diags = diagnose(levels, system, system_diag, trends, plateau, x_max, est.mu, est.servers, est.autoconsistent)

    evals = [_evaluate(c, levels, est, system, rej_relevant) for c in CANDIDATES]
    eligible = [e for e in evals if e.eligible and e.score_pct is not None]
    by_key = {c.key: c for c in CANDIDATES}

    def pick(pool: list[Evaluation]) -> Evaluation:
        best = min(e.score_pct for e in pool)
        near = [e for e in pool if e.score_pct - best <= T.TIE_PP]
        return min(near, key=lambda e: by_key[e.key].parsimony)

    rec = nearest = None
    status = "no_good_fit"
    if eligible:
        rec = pick(eligible)
        status = "recommended" if rec.score_pct <= T.NO_FIT_SCORE else "no_good_fit"
        if status == "no_good_fit":
            nearest, rec = rec, None
    else:
        structural = [e for e in evals if e.score_pct is not None
                      and all(r.passed or r.soft for r in e.rules)
                      and next(r for r in e.rules if r.id == "estrutura").passed]
        if structural:
            nearest = pick(structural)

    chosen = rec or nearest
    others = sorted([e for e in eligible if e is not chosen], key=lambda e: e.score_pct)
    confidence = _confidence(rec, others[0] if others else None, est, levels, diags, status)

    warnings = list(est.notes)
    if system == "closed":
        warnings.insert(0, "O teste de carga é um sistema fechado (cada usuário só envia a próxima requisição depois da "
                           "resposta), diferente do M/M/1 aberto. Os modelos de população finita (M/M/1//N, M/M/c//N) "
                           "são a alternativa adequada; divergências podem vir dessa diferença estrutural.")
    if status == "no_good_fit":
        warnings.append("Nenhum modelo do catálogo se ajusta bem a estes dados; o resultado indica o mais próximo, com ressalvas.")
    if status == "no_good_fit" and any(d.id == "V2" and d.status == CRITICAL for d in diags):
        warnings.append("Há sobrecarga sem rejeições: nenhum modelo de capacidade infinita é estável. Reduza a taxa de chegada "
                        "do teste, ou informe a capacidade (K) e o número de servidores se o sistema os limita.")
    if any(d.id == "V6" and d.status != "ok" for d in diags):
        warnings.append("Os dados fogem da hipótese exponencial; espere erros maiores mesmo no modelo estruturalmente correto.")

    ranking = []
    ordered = sorted(evals, key=lambda e: (not e.eligible, e.score_pct if e.score_pct is not None else 1e9,
                                           by_key[e.key].parsimony))
    for e in ordered:
        ranking.append({
            "key": e.key, "notation": e.notation, "eligible": e.eligible, "score_pct": e.score_pct,
            "scored_metrics": e.scored_metrics, "mu": e.mu_used,
            "recommended": e is rec, "reasons": e.reasons, "error_pct": e.error_pct, "penalty_pp": e.penalty_pp,
            "criteria": [{"id": r.id, "passed": r.passed, "reason": r.reason} for r in e.rules],
        })

    comparison = []
    if chosen is not None and chosen.mu_used is not None:
        comparison = compare_to_observed(by_key[chosen.key], est, chosen.mu_used, levels)

    def brief(e: Evaluation | None) -> dict | None:
        if e is None:
            return None
        return {"key": e.key, "notation": e.notation, "score_pct": e.score_pct, "mu": e.mu_used,
                "servers": _servers(by_key[e.key], est), "capacity": est.capacity if by_key[e.key].finite_capacity else None,
                "population": levels[-1].users if by_key[e.key].family == "closed" else None,
                "think_time": est.think_time if by_key[e.key].family == "closed" else None}

    return AnalysisResult(
        status=status, confidence=confidence, recommended=brief(rec), nearest=brief(nearest),
        ranking=ranking, rationale=_rationale(system, rec, nearest, evals, est, levels, status, confidence, rej),
        warnings=warnings, diagnostics=diags, system_type=system, estimates=est, overall=overall,
        levels=[{"users": lv.users, "metrics": asdict(lv.metrics)} for lv in levels], comparison=comparison,
        dataset={"rows": total_rows, "rows_analyzed": len(ds), "labels": sorted({str(x) for x in ds.label})[:50],
                 "start": float(ds.start[0]), "end": float(ds.end.max())},
        service_hint=service_hint(levels),
    )


def service_hint(levels: list[LoadLevel]) -> dict | None:
    """Sugestão de modelo pelo CV dos tempos de resposta do **menor nível de carga** (Fase 13, RFC-26).

    O JMeter só registra o tempo de resposta (serviço + espera na fila). Com carga baixa a espera é
    pequena e o CV da resposta se aproxima do CV do serviço; com carga alta ele mistura os dois. Por isso é
    uma indicação, e o ajuste da aba "Ajustar distribuição" (com a amostra dos tempos de serviço) é quem decide.
    Não entra no ranking nem nos escores do recomendador.
    """
    cv = levels[0].metrics.response_cv
    if cv is None:
        return None
    suggestion = suggest_from_cv(cv, SERVICE).as_dict()
    users = levels[0].users
    suggestion["basis"] = (
        "CV dos tempos de resposta" + (f" no nível de {users} usuários" if users else " da janela analisada")
        + " (serviço + espera): aproxima o CV do serviço quando a carga é baixa."
    )
    return suggestion


def compare_chosen(
    key: str, levels: list[LoadLevel], mu: float, servers: int = 1,
    capacity: int | None = None, think_time: float | None = None,
) -> tuple[str, list[dict]]:
    """Compara a medição com um modelo escolhido pelo usuário (RF-24), sem refazer a análise.

    `levels` vem do resultado de `analyze`. Devolve (notação, comparação por nível).
    """
    cand = next((c for c in CANDIDATES if c.key == key), None)
    if cand is None:
        raise QueueValidationError(f"model deve ser um de: {', '.join(c.key for c in CANDIDATES)}.", "model")
    if cand.finite_capacity and capacity is None:
        raise QueueValidationError("capacity é obrigatório para modelos de capacidade finita.", "capacity")
    if cand.family == "closed":
        if think_time is None:
            raise QueueValidationError("think_time é obrigatório para modelos de população finita.", "think_time")
        if any(not lv.users for lv in levels):
            raise QueueValidationError("Cada nível precisa informar o número de usuários (users).", "levels")
    est = Estimates(mu, "informado", servers if cand.multi_server else 1, "informado",
                    think_time, "informado" if think_time is not None else None,
                    capacity, "informado" if capacity is not None else None)
    return cand.notation(est, levels), compare_to_observed(cand, est, mu, levels)
