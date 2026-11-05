"""Duas sessões lado a lado, por exemplo manhã × tarde (Fase 13.2).

Recebe duas respostas de `/video/estimate` e compara, por aproximação, o que o modelo usa: ciclo e fases, taxa de
chegada, ℓ, h e amarelo utilizável. Para cada grandeza devolve os dois valores, a diferença e, quando há como
calcular, um p-valor:

- taxa de chegada: teste binomial exato condicional (dado o total de chegadas das duas sessões, a parcela da sessão A
  é Binomial(n, tempo_A / (tempo_A + tempo_B)) se as taxas forem iguais); a razão das taxas traz IC pelo método exato
  (Clopper–Pearson sobre a parcela). Vale para contagens de Poisson; chegadas em pelotão têm mais variância e o p-valor
  seria otimista (o sistema já avisa isso na estimação).
- ℓ e h: teste z para a diferença, com o erro-padrão recuperado do IC de cada estimativa (metade da largura / t).
  Aproximado: é o que dá para recuperar sem os dados brutos.
- ciclo, verde, amarelo, todo-vermelho e amarelo utilizável: só os valores e a diferença (não há erro-padrão).

Dois ou mais testes por linha não são corrigidos entre si: a tabela é descritiva, e o p-valor serve para apontar
onde olhar primeiro.
"""

import math

from scipy import stats

from app.domain.validation.errors import QueueValidationError

_APPROACH_KEYS = ("a1", "a2", "a3", "a4")


def _get(d: object, *path):
    for p in path:
        if d is None:
            return None
        try:
            d = d[p]
        except (KeyError, IndexError, TypeError):
            return None
    return d


def _num(x) -> float | None:
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) else None


def _row(group: str, name: str, unit: str, a: float | None, b: float | None, *, p: float | None = None, ratio: float | None = None,
         ratio_ci: list[float] | None = None, note: str | None = None) -> dict:
    return {"group": group, "name": name, "unit": unit, "a": a, "b": b,
            "difference": None if a is None or b is None else b - a, "ratio": ratio, "ratio_ci": ratio_ci,
            "p_value": p, "note": note}


def _se_from_ci(low, high, level: float) -> float | None:
    low, high = _num(low), _num(high)
    if low is None or high is None or high <= low:
        return None
    return (high - low) / (2 * float(stats.norm.ppf((1 + level) / 2)))


def _z_test(a: dict | None, b: dict | None, level_a: float, level_b: float) -> float | None:
    if not a or not b:
        return None
    ma, mb = _num(a.get("mean")), _num(b.get("mean"))
    sa = _se_from_ci(a.get("ci_low"), a.get("ci_high"), level_a)
    sb = _se_from_ci(b.get("ci_low"), b.get("ci_high"), level_b)
    if None in (ma, mb, sa, sb):
        return None
    z = (mb - ma) / math.sqrt(sa ** 2 + sb ** 2)
    return float(2 * stats.norm.sf(abs(z)))


def _rate_test(arrivals_a: int, span_a: float, arrivals_b: int, span_b: float, level: float) -> tuple[float | None, float | None, list[float] | None]:
    n = arrivals_a + arrivals_b
    if n == 0 or span_a <= 0 or span_b <= 0:
        return None, None, None
    share = span_a / (span_a + span_b)
    result = stats.binomtest(arrivals_a, n, share, alternative="two-sided")
    ci = result.proportion_ci(confidence_level=level, method="exact")
    # parcela de A → razão de taxas B/A:  rate_b / rate_a = (n − k) / k · span_a / span_b
    def to_ratio(prop: float) -> float | None:
        return None if prop <= 0 or prop >= 1 else (1 - prop) / prop * (span_a / span_b)
    low, high = to_ratio(ci.high), to_ratio(ci.low)
    ratio = (arrivals_b / span_b) / (arrivals_a / span_a) if arrivals_a > 0 else None
    return float(result.pvalue), ratio, [x for x in (low, high)] if low is not None and high is not None else None


def compare_estimates(a: dict, b: dict, labels: tuple[str, str] = ("A", "B"), level: float = 0.95) -> dict:
    """`a` e `b`: respostas de /video/estimate. Mesmo nº de aproximações; a ordem é a das fases."""
    if not isinstance(a, dict) or not isinstance(b, dict) or "signal" not in a or "signal" not in b:
        raise QueueValidationError("a e b devem ser respostas de /video/estimate.", "a")
    n = len(_get(a, "signal", "phases") or [])
    if n != len(_get(b, "signal", "phases") or []):
        raise QueueValidationError("As duas sessões têm números de aproximações diferentes.", "b")
    if not (isinstance(level, (int, float)) and 0 < level < 1):
        raise QueueValidationError("level deve estar entre 0 e 1.", "level")
    rows: list[dict] = []
    notes: list[str] = []
    la = _num(_get(a, "method", "confidence_level")) or 0.95
    lb = _num(_get(b, "method", "confidence_level")) or 0.95

    rows.append(_row("plano", "Ciclo", "s", _num(_get(a, "signal", "cycle", "mean")), _num(_get(b, "signal", "cycle", "mean"))))
    for i in range(n):
        for field, label in (("green", "Verde"), ("amber", "Amarelo"), ("all_red", "Todo-vermelho")):
            rows.append(_row("plano", f"{label} da fase {i + 1}", "s", _num(_get(a, "signal", "phases", i, field)),
                             _num(_get(b, "signal", "phases", i, field))))
    for key in _APPROACH_KEYS[:n]:
        who = f"Aproximação {key[1]}"
        aa, bb = _get(a, "arrivals", key), _get(b, "arrivals", key)
        if aa and bb:
            span_a = sum(x["duration"] for x in aa["blocks"])
            span_b = sum(x["duration"] for x in bb["blocks"])
            p, ratio, ci = _rate_test(int(aa["arrivals"]), span_a, int(bb["arrivals"]), span_b, level)
            rows.append(_row(who, "Taxa de chegada", "veíc/s", _num(aa["mean_rate"]), _num(bb["mean_rate"]), p=p, ratio=ratio, ratio_ci=ci,
                             note="Teste binomial exato; supõe chegadas de Poisson."))
        da, db = _get(a, "discharge", key), _get(b, "discharge", key)
        rows.append(_row(who, "ℓ (1º veículo)", "s", _num(_get(da, "first_vehicle_time", "mean")), _num(_get(db, "first_vehicle_time", "mean")),
                         p=_z_test(_get(da, "first_vehicle_time"), _get(db, "first_vehicle_time"), la, lb),
                         note="p-valor aproximado, a partir dos ICs."))
        rows.append(_row(who, "h (intervalo por carro)", "s", _num(_get(da, "headway", "mean")), _num(_get(db, "headway", "mean")),
                         p=_z_test(_get(da, "headway"), _get(db, "headway"), la, lb), note="p-valor aproximado, a partir dos ICs."))
        rows.append(_row(who, "Amarelo utilizável (limite inferior)", "s", _num(_get(da, "amber_usable", "value")),
                         _num(_get(db, "amber_usable", "value"))))
    for r in rows:
        if r["a"] is None and r["b"] is None:
            r["note"] = (r["note"] + " " if r["note"] else "") + "Não estimado em nenhuma das sessões."
    if a.get("classes") or b.get("classes"):
        notes.append("Com classes de veículos, h e ℓ são por carro equivalente com os fatores de cada sessão.")
    return {"labels": list(labels), "level": level, "rows": rows, "notes": notes,
            "sessions": [{"label": labels[0], "session_id": a.get("session_id"), "horizon": a.get("horizon")},
                         {"label": labels[1], "session_id": b.get("session_id"), "horizon": b.get("horizon")}]}
