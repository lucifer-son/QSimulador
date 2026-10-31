"""Dados do vídeo (Fase 13.1): leitura das planilhas do protocolo, estimação e validação.

Planilhas (CSV, vírgula, ponto-e-vírgula ou tabulação; decimal com ponto ou vírgula; tempos em
segundos do vídeo ou hh:mm:ss). Cada tabela pode ter várias sessões; informe `session_id` se houver mais de uma.

- **eventos semafóricos** (obrigatória): `timestamp`, `approach_id`, `signal_state` (verde/amarelo/vermelho).
  Uma linha por mudança de estado de cada aproximação.
- **contagens** (obrigatória): `interval_start`, `interval_end`, `approach_id`, `arrivals`, `departures`,
  e opcionais `queue_count` (fila no fim do intervalo), `queue_visible` (a fila inteira estava visível?)
  e `queue_count_start` (fila no início do intervalo, usada só no primeiro).
- **cruzamentos** (opcional, necessária para estimar ℓ, h e o amarelo utilizável): `crossing_time`, `approach_id`.
- **trajetórias amostradas** (opcional): `approach_id`, `queue_arrival_time`, `crossing_time`, `complete_observation`.

Nada é preenchido por suposição: célula vazia é dado ausente. Onde um valor ausente impediria o
cálculo, a leitura recusa o arquivo e diz a linha; os parâmetros que não puderem ser estimados
voltam como `null` e viram o aviso `not_informed` no cruzamento.

O tempo zero da simulação é o início do primeiro intervalo de contagem da sessão.
"""

import csv
import io
import math
from dataclasses import dataclass
from numbers import Real

import numpy as np
from scipy import stats

from app.analysis.fit import fit_sample
from app.domain.validation.errors import InvalidDatasetError, QueueValidationError
from app.traffic.plan import APPROACH_KEYS

MAX_ROWS = 200_000
DEFAULT_MAX_HEADWAY = 4.0     # s: intervalo máximo entre veículos para ainda contar como descarga saturada
DEFAULT_MIN_RUN = 5           # veículos: tamanho mínimo da sequência saturada de um verde
DEFAULT_PROFILE_BLOCK = 900.0  # s: o perfil sugerido junta as contagens em blocos de 15 min (protocolo)
DEFAULT_CORE = 8              # veículos da cabeça da fila usados no ajuste da reta de descarga
MIN_CYCLES = 2
MIN_SATURATED_CYCLES = 3
FIXED_TIME_CV = 0.03          # CV do ciclo acima do qual o plano deixa de parecer de tempo fixo

_ALIASES = {
    "timestamp": ("timestamp", "time", "tempo", "instante", "t"),
    "approach_id": ("approach_id", "approach", "aproximacao", "aproximação", "via"),
    "signal_state": ("signal_state", "state", "estado", "fase_estado", "cor"),
    "session_id": ("session_id", "session", "sessao", "sessão"),
    "interval_start": ("interval_start", "inicio", "início", "start"),
    "interval_end": ("interval_end", "fim", "end"),
    "arrivals": ("arrivals", "chegadas"),
    "departures": ("departures", "saidas", "saídas"),
    "queue_count": ("queue_count", "fila"),
    "queue_visible": ("queue_visible", "fila_visivel", "fila_visível"),
    "queue_count_start": ("queue_count_start", "fila_inicio", "fila_início"),
    "crossing_time": ("crossing_time", "cruzamento", "passagem"),
    "queue_arrival_time": ("queue_arrival_time", "chegada_fila"),
    "complete_observation": ("complete_observation", "completa", "observacao_completa"),
}
_STATES = {
    "green": "green", "verde": "green", "g": "green", "v": "green",
    "amber": "amber", "yellow": "amber", "amarelo": "amber", "a": "amber",
    "red": "red", "vermelho": "red", "r": "red",
}
_TRUE = {"1", "true", "t", "sim", "s", "yes", "y", "verdadeiro"}
_FALSE = {"0", "false", "f", "nao", "não", "n", "no", "falso"}


def _fail(table: str, message: str, row: int | None = None) -> InvalidDatasetError:
    where = f" (linha {row})" if row else ""
    return InvalidDatasetError(f"{table}: {message}{where}", table)


# ---------- leitura ----------

def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise InvalidDatasetError("Não foi possível ler a codificação do arquivo.", "file")


def _number(text: str, table: str, column: str, row: int, *, decimal_comma: bool) -> float:
    t = text.strip()
    if ":" in t:
        parts = t.replace(",", ".").split(":")
        try:
            values = [float(p) for p in parts]
        except ValueError:
            raise _fail(table, f"coluna {column} com horário inválido “{text}”", row) from None
        if len(values) not in (2, 3) or any(v < 0 for v in values):
            raise _fail(table, f"coluna {column} com horário inválido “{text}”", row)
        seconds = 0.0
        for v in values:
            seconds = seconds * 60 + v
        return seconds
    if decimal_comma:
        t = t.replace(",", ".")
    try:
        value = float(t)
    except ValueError:
        raise _fail(table, f"coluna {column} com valor não numérico “{text}”", row) from None
    if not math.isfinite(value):
        raise _fail(table, f"coluna {column} com valor não finito", row)
    return value


def read_table(content: bytes, table: str, required: tuple[str, ...], optional: tuple[str, ...] = ()) -> list[dict]:
    """Lê o CSV e devolve as linhas com os nomes canônicos das colunas ("" vira None)."""
    text = _decode(content)
    if not text.strip():
        raise _fail(table, "o arquivo está vazio")
    sample = text[:4096]
    delimiter = max(",;\t", key=sample.count) if any(c in sample for c in ",;\t") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    try:
        header = [h.strip().lower() for h in next(reader)]
    except StopIteration:
        raise _fail(table, "o arquivo está vazio") from None
    index: dict[str, int] = {}
    for canonical in (*required, *optional, "session_id"):
        for alias in _ALIASES[canonical]:
            if alias in header:
                index[canonical] = header.index(alias)
                break
    missing = [c for c in required if c not in index]
    if missing:
        raise _fail(table, "faltam as colunas " + ", ".join(missing) + f". Encontradas: {', '.join(header)}")
    decimal_comma = delimiter == ";"
    rows = []
    for number, raw in enumerate(reader, start=2):
        if not any(cell.strip() for cell in raw):
            continue
        if len(rows) >= MAX_ROWS:
            raise _fail(table, f"mais de {MAX_ROWS} linhas")
        row = {"_row": number}
        for name, position in index.items():
            cell = raw[position].strip() if position < len(raw) else ""
            row[name] = cell if cell != "" else None
        rows.append(row)
    if not rows:
        raise _fail(table, "não há linhas de dados")
    for r in rows:
        r["_dc"] = decimal_comma
    return rows


def _num(row: dict, column: str, table: str, *, required: bool = True) -> float | None:
    value = row.get(column)
    if value is None:
        if required:
            raise _fail(table, f"coluna {column} vazia (dado ausente)", row["_row"])
        return None
    return _number(value, table, column, row["_row"], decimal_comma=row["_dc"])


def _flag(row: dict, column: str, table: str) -> bool | None:
    value = row.get(column)
    if value is None:
        return None
    v = value.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    raise _fail(table, f"coluna {column} deve ser sim/não, 1/0 ou verdadeiro/falso (veio “{value}”)", row["_row"])


# ---------- sessão ----------

SIGNAL_TABLE, COUNTS_TABLE, CROSSINGS_TABLE, TRACKS_TABLE = "signal_events", "counts", "crossings", "trajectories"


@dataclass
class Session:
    session_id: str | None
    approach_ids: tuple[str, str]
    signal: dict[str, list[tuple[float, str]]]          # approach_id -> [(t, estado)], ordenado, t em relação a t0
    counts: dict[str, list[dict]]                       # approach_id -> intervalos ordenados (t em relação a t0)
    crossings: dict[str, np.ndarray] | None
    tracks: dict[str, list[tuple[float, float, bool]]] | None
    t0: float
    horizon: float
    notes: list[str]


def _pick_session(rows: list[dict], table: str, session_id: str | None) -> list[dict]:
    ids = sorted({r["session_id"] for r in rows if r.get("session_id")})
    if session_id is not None:
        chosen = [r for r in rows if r.get("session_id") == session_id]
        if not chosen:
            raise _fail(table, f"não há linhas da sessão “{session_id}”. Sessões: {', '.join(ids) or '(sem session_id)'}")
        return chosen
    if len(ids) > 1:
        raise _fail(table, f"o arquivo tem várias sessões ({', '.join(ids)}). Informe session_id.")
    return rows


def _resolve_approaches(all_ids: set[str], requested: tuple[str, str] | None) -> tuple[str, str]:
    if requested is not None:
        if len(set(requested)) != 2:
            raise QueueValidationError("approach_ids deve ter dois identificadores diferentes.", "approach_ids")
        missing = [a for a in requested if a not in all_ids]
        if missing:
            raise InvalidDatasetError(
                f"approach_id não encontrado nos dados: {', '.join(missing)}. Encontrados: {', '.join(sorted(all_ids))}.", "approach_ids")
        return requested
    if len(all_ids) != 2:
        raise InvalidDatasetError(
            f"Os dados têm {len(all_ids)} aproximações ({', '.join(sorted(all_ids))}); o modelo tem duas. "
            "Informe approach_ids com as duas que serão estudadas.", "approach_ids")
    first, second = sorted(all_ids)
    return first, second


def load_session(
    signal_csv: bytes, counts_csv: bytes, crossings_csv: bytes | None = None, tracks_csv: bytes | None = None,
    *, session_id: str | None = None, approach_ids: tuple[str, str] | None = None,
) -> Session:
    sig_rows = _pick_session(read_table(signal_csv, SIGNAL_TABLE, ("timestamp", "approach_id", "signal_state")), SIGNAL_TABLE, session_id)
    cnt_rows = _pick_session(
        read_table(counts_csv, COUNTS_TABLE, ("interval_start", "interval_end", "approach_id", "arrivals"),
                   ("departures", "queue_count", "queue_visible", "queue_count_start")), COUNTS_TABLE, session_id)
    ids = {r["approach_id"] for r in cnt_rows if r["approach_id"]}
    chosen = _resolve_approaches(ids, approach_ids)
    notes: list[str] = []

    # contagens
    counts: dict[str, list[dict]] = {}
    for a in chosen:
        items = []
        for r in (x for x in cnt_rows if x["approach_id"] == a):
            start, end = _num(r, "interval_start", COUNTS_TABLE), _num(r, "interval_end", COUNTS_TABLE)
            if end <= start:
                raise _fail(COUNTS_TABLE, "interval_end deve ser maior que interval_start", r["_row"])
            arrivals = _num(r, "arrivals", COUNTS_TABLE)
            if arrivals < 0 or arrivals != int(arrivals):
                raise _fail(COUNTS_TABLE, "arrivals deve ser um inteiro maior ou igual a 0", r["_row"])
            dep = _num(r, "departures", COUNTS_TABLE, required=False)
            if dep is not None and (dep < 0 or dep != int(dep)):
                raise _fail(COUNTS_TABLE, "departures deve ser um inteiro maior ou igual a 0", r["_row"])
            q = _num(r, "queue_count", COUNTS_TABLE, required=False)
            if q is not None and (q < 0 or q != int(q)):
                raise _fail(COUNTS_TABLE, "queue_count deve ser um inteiro maior ou igual a 0", r["_row"])
            q0 = _num(r, "queue_count_start", COUNTS_TABLE, required=False)
            items.append({
                "start": start, "end": end, "arrivals": int(arrivals), "departures": None if dep is None else int(dep),
                "queue": None if q is None else int(q), "queue_visible": _flag(r, "queue_visible", COUNTS_TABLE),
                "queue_start": None if q0 is None else int(q0), "row": r["_row"],
            })
        items.sort(key=lambda d: d["start"])
        if not items:
            raise _fail(COUNTS_TABLE, f"a aproximação {a} não tem intervalos")
        for prev, cur in zip(items, items[1:]):
            if cur["start"] < prev["end"] - 1e-9:
                raise _fail(COUNTS_TABLE, f"intervalos sobrepostos em {a}", cur["row"])
            if cur["start"] > prev["end"] + 1e-9:
                raise _fail(COUNTS_TABLE, f"há uma lacuna entre {prev['end']:g} s e {cur['start']:g} s em {a}: "
                            "o perfil de chegadas precisa de intervalos contíguos", cur["row"])
        counts[a] = items
    t0 = min(items[0]["start"] for items in counts.values())
    for a, items in counts.items():
        if abs(items[0]["start"] - t0) > 1e-9:
            raise _fail(COUNTS_TABLE, f"as aproximações começam em instantes diferentes ({a} em {items[0]['start']:g} s e outra em {t0:g} s)")
    horizon = min(items[-1]["end"] for items in counts.values()) - t0
    for items in counts.values():
        for d in items:
            d["start"] -= t0
            d["end"] -= t0
    if any(items[-1]["end"] - t0 > horizon + 1e-9 for items in counts.values()):
        notes.append("As aproximações têm durações de contagem diferentes: a simulação usa a menor.")

    # eventos semafóricos
    signal: dict[str, list[tuple[float, str]]] = {}
    for a in chosen:
        events = []
        for r in (x for x in sig_rows if x["approach_id"] == a):
            raw_state = (r["signal_state"] or "").strip().lower()
            if raw_state not in _STATES:
                raise _fail(SIGNAL_TABLE, f"signal_state “{r['signal_state']}” desconhecido (use verde, amarelo ou vermelho)", r["_row"])
            events.append((_num(r, "timestamp", SIGNAL_TABLE) - t0, _STATES[raw_state]))
        events.sort()
        deduped: list[tuple[float, str]] = []
        for t, s in events:
            if not deduped or deduped[-1][1] != s:
                deduped.append((t, s))
        if len(deduped) < 3:
            raise _fail(SIGNAL_TABLE, f"a aproximação {a} tem poucos eventos semafóricos")
        signal[a] = deduped

    crossings = None
    if crossings_csv:
        rows = _pick_session(read_table(crossings_csv, CROSSINGS_TABLE, ("crossing_time", "approach_id")), CROSSINGS_TABLE, session_id)
        crossings = {a: np.sort(np.array([_num(r, "crossing_time", CROSSINGS_TABLE) - t0 for r in rows if r["approach_id"] == a])) for a in chosen}
    tracks = None
    if tracks_csv:
        rows = _pick_session(read_table(tracks_csv, TRACKS_TABLE, ("approach_id", "queue_arrival_time", "crossing_time"),
                                        ("complete_observation",)), TRACKS_TABLE, session_id)
        tracks = {a: [] for a in chosen}
        for r in rows:
            if r["approach_id"] in tracks:
                complete = _flag(r, "complete_observation", TRACKS_TABLE)
                arr = _num(r, "queue_arrival_time", TRACKS_TABLE, required=False)
                cr = _num(r, "crossing_time", TRACKS_TABLE, required=False)
                ok = complete is not False and arr is not None and cr is not None
                tracks[r["approach_id"]].append((arr - t0 if arr is not None else math.nan, cr - t0 if cr is not None else math.nan, ok))
    return Session(session_id, chosen, signal, counts, crossings, tracks, t0, horizon, notes)


# ---------- estimação ----------

def _stat(values: list[float]) -> dict | None:
    if not values:
        return None
    a = np.asarray(values, float)
    return {"mean": float(a.mean()), "std": float(a.std(ddof=1)) if len(a) > 1 else None,
            "min": float(a.min()), "max": float(a.max()), "n": int(len(a))}


def _transitions(events: list[tuple[float, str]], state: str) -> list[float]:
    return [t for t, s in events if s == state]


def _next_after(times: list[float], t: float) -> float | None:
    return next((x for x in times if x > t), None)


def estimate_signal(session: Session) -> dict:
    a1, a2 = session.approach_ids
    ev1, ev2 = session.signal[a1], session.signal[a2]
    g1, am1, r1 = (_transitions(ev1, s) for s in ("green", "amber", "red"))
    g2, am2, r2 = (_transitions(ev2, s) for s in ("green", "amber", "red"))
    if len(g1) < MIN_CYCLES + 1 or len(g2) < MIN_CYCLES:
        raise InvalidDatasetError(
            f"São necessários ao menos {MIN_CYCLES} ciclos completos de cada aproximação nos eventos semafóricos.", SIGNAL_TABLE)

    def durations(greens, ambers, reds):
        green, amber = [], []
        for g in greens:
            a = _next_after(ambers, g)
            r = _next_after(reds, g)
            if r is None:
                continue
            if a is not None and a < r:
                green.append(a - g)
                amber.append(r - a)
            else:
                green.append(r - g)            # sem amarelo registrado: verde vai direto ao vermelho
                amber.append(0.0)
        return green, amber

    green1, amber1 = durations(g1, am1, r1)
    green2, amber2 = durations(g2, am2, r2)
    all_red1 = [x - r for r in r1 if (x := _next_after(g2, r)) is not None and x - r < 60]
    all_red2 = [x - r for r in r2 if (x := _next_after(g1, r)) is not None and x - r < 60]
    cycles = [b - a for a, b in zip(g1, g1[1:])]
    if len(cycles) < MIN_CYCLES:
        raise InvalidDatasetError(f"Apenas {len(cycles)} ciclo(s) completo(s) da aproximação {a1}: são necessários {MIN_CYCLES}.", SIGNAL_TABLE)

    warnings = []
    cycle_stat = _stat(cycles)
    cv = (cycle_stat["std"] or 0.0) / cycle_stat["mean"]
    if cv > FIXED_TIME_CV or cycle_stat["max"] - cycle_stat["min"] > 3:
        warnings.append({
            "code": "not_fixed_time", "level": "warning",
            "message": (f"O ciclo observado varia de {cycle_stat['min']:.1f} a {cycle_stat['max']:.1f} s (CV {cv:.1%}): o plano "
                        "não parece de tempo fixo. O modelo usa as médias; confira se isso é aceitável para o seu cruzamento."),
        })
    phases = [
        {"green": _mean(green1), "amber": _mean(amber1), "all_red": _mean(all_red1)},
        {"green": _mean(green2), "amber": _mean(amber2), "all_red": _mean(all_red2)},
    ]
    total = sum(sum(v for v in p.values() if v is not None) for p in phases)
    if abs(total - cycle_stat["mean"]) > max(1.0, 0.03 * cycle_stat["mean"]):
        warnings.append({
            "code": "cycle_mismatch", "level": "warning",
            "message": (f"As fases somam {total:.1f} s, mas o ciclo medido é {cycle_stat['mean']:.1f} s: há estados ausentes "
                        "ou não registrados (por exemplo, fases que o modelo não representa)."),
        })

    # instante do ciclo em t = 0
    before = [g for g in g1 if g <= 1e-9]
    if before:
        offset, source = -max(before), "observed"
    else:
        offset, source = (-min(g1)) % cycle_stat["mean"], "extrapolated"
        warnings.append({
            "code": "offset_extrapolated", "level": "warning",
            "message": "Nenhum verde da aproximação 1 foi registrado antes do início da contagem: o offset foi extrapolado com o ciclo médio."})
    return {
        "approach_ids": [a1, a2], "phases": phases, "offset": float(offset), "offset_source": source,
        "cycle": cycle_stat, "green": [_stat(green1), _stat(green2)], "amber": [_stat(amber1), _stat(amber2)],
        "all_red": [_stat(all_red1), _stat(all_red2)], "warnings": warnings,
    }


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _poisson_ci(k: int, duration: float, level: float) -> tuple[float, float]:
    alpha = 1 - level
    low = 0.0 if k == 0 else stats.chi2.ppf(alpha / 2, 2 * k) / 2 / duration
    high = stats.chi2.ppf(1 - alpha / 2, 2 * k + 2) / 2 / duration
    return float(low), float(high)


def estimate_arrivals(session: Session, level: float = 0.95) -> dict:
    out = {}
    for key, a in zip(APPROACH_KEYS, session.approach_ids):
        items = session.counts[a]
        blocks = []
        for d in items:
            duration = d["end"] - d["start"]
            low, high = _poisson_ci(d["arrivals"], duration, level)
            blocks.append({"start": d["start"], "duration": duration, "arrivals": d["arrivals"],
                           "lam": d["arrivals"] / duration, "ci_low": low, "ci_high": high})
        total = sum(b["arrivals"] for b in blocks)
        span = sum(b["duration"] for b in blocks)
        low, high = _poisson_ci(total, span, level)
        initial = items[0]["queue_start"]
        visible = items[0]["queue_visible"]
        out[key] = {
            "approach_id": a, "blocks": blocks, "mean_rate": total / span, "mean_rate_ci": [low, high], "arrivals": total,
            "initial_queue": initial if (initial is not None and visible is not False) else None,
        }
    return out


def estimate_discharge(
    session: Session, signal: dict, *, max_headway: float, min_run: int, core: int, level: float = 0.95,
) -> dict | None:
    """ℓ, h (com distribuição sugerida) e amarelo utilizável por aproximação, a partir dos cruzamentos.

    Em cada verde, a *sequência saturada* é a que começa no primeiro cruzamento e segue enquanto o
    intervalo entre veículos não passa de `max_headway`; só vale se tiver ao menos `min_run` veículos.
    Dos veículos dessa sequência usam-se os `core` primeiros (a cabeça da fila, onde ainda há fila
    de verdade) e ajusta-se, em todos os verdes juntos, a reta

        instante do n-ésimo veículo − início do verde = ℓ + (n − 1) · h

    por mínimos quadrados: a inclinação é o intervalo h entre veículos e o intercepto é ℓ. A reta
    absorve a partida mais lenta dos primeiros veículos, e é exatamente o que o motor reproduz
    (1º veículo em ℓ, depois um a cada h). Os intervalos entre veículos consecutivos da cabeça da
    fila alimentam o ajuste da distribuição. Verdes cortados pelo início ou pelo fim da gravação ficam de fora.
    """
    if session.crossings is None:
        return None
    out = {}
    for key, a in zip(APPROACH_KEYS, session.approach_ids):
        ev = session.signal[a]
        greens, ambers, reds = (_transitions(ev, s) for s in ("green", "amber", "red"))
        times = session.crossings[a]
        index_list: list[int] = []
        offset_list: list[float] = []
        gaps: list[float] = []
        first_raw: list[float] = []
        used, amber_extra, pressured = 0, [], 0
        for g in greens:
            red = _next_after(reds, g)
            if red is None or g < 0 or red > session.horizon + 1e-9:
                continue                      # verde cortado pelo início ou pelo fim da gravação: não dá para medir a descarga
            amber = _next_after(ambers, g)
            amber_start = amber if (amber is not None and amber < red) else red
            inside = times[(times >= g) & (times < red)]
            if len(inside) == 0:
                continue
            run = [inside[0]]
            for t in inside[1:]:
                if t - run[-1] <= max_headway:
                    run.append(t)
                else:
                    break
            if len(run) < min_run:
                continue
            used += 1
            head = run[:core]
            index_list.extend(range(len(head)))
            offset_list.extend(t - g for t in head)
            gaps.extend(np.diff(head).tolist())
            first_raw.append(run[0] - g)
            if run[-1] >= amber_start - max_headway:           # a fila ainda pressionava no fim do verde
                pressured += 1
                if run[-1] >= amber_start:                     # e alguém cruzou já no amarelo
                    amber_extra.append(min(run[-1] - amber_start, red - amber_start))
        in_red = int(sum(((times >= r) & (times < (_next_after(greens, r) or math.inf))).sum() for r in reds))
        item: dict = {"approach_id": a, "saturated_cycles": used, "crossings_in_red": in_red,
                      "first_vehicle_time": None, "headway": None, "amber_usable": None, "notes": []}
        if used < MIN_SATURATED_CYCLES:
            item["notes"].append(
                f"Só {used} verde(s) com fila saturada (pelo menos {min_run} veículos com intervalos ≤ {max_headway:g} s): "
                f"são necessários {MIN_SATURATED_CYCLES}. ℓ, h e o amarelo utilizável não foram estimados.")
            out[key] = item
            continue

        x = np.asarray(index_list, float)
        y = np.asarray(offset_list, float)
        n = len(x)
        slope, intercept = np.polyfit(x, y, 1)
        resid = y - (intercept + slope * x)
        s2 = float((resid ** 2).sum() / (n - 2))
        sxx = float(((x - x.mean()) ** 2).sum())
        se_slope = math.sqrt(s2 / sxx)
        se_int = math.sqrt(s2 * (1 / n + x.mean() ** 2 / sxx))
        tcrit = float(stats.t.ppf((1 + level) / 2, n - 2))
        item["first_vehicle_time"] = {
            "mean": float(intercept), "ci_low": float(intercept - tcrit * se_int), "ci_high": float(intercept + tcrit * se_int),
            "n": used, "first_crossing_mean": float(np.mean(first_raw)),
            "method": "intercepto da reta de descarga (extrapolado ao 1º veículo)",
        }
        gaps_arr = np.asarray([g for g in gaps if g > 0], float)
        h_mean = float(slope)
        headway = {"n": int(len(gaps_arr)), "mean": h_mean, "ci_low": float(slope - tcrit * se_slope),
                   "ci_high": float(slope + tcrit * se_slope), "std": float(gaps_arr.std(ddof=1)),
                   "cv": float(gaps_arr.std(ddof=1) / gaps_arr.mean()), "fit": None, "suggestion": None}
        if len(gaps_arr) >= 10:
            try:
                fit = fit_sample(gaps_arr.tolist(), bootstrap=0, seed=1)
                spec = dict(fit["service_suggestion"]) if fit["service_suggestion"] else None
                if spec and "mean" in spec:
                    spec["mean"] = h_mean              # a média do modelo é a inclinação da reta (a que preserva a capacidade)
                headway["fit"] = {"best": fit["best"], "cv": fit["cv"], "service_suggestion": spec}
                headway["suggestion"] = spec
            except QueueValidationError:
                pass
        if headway["suggestion"] is None:
            headway["suggestion"] = ({"distribution": "deterministic", "mean": h_mean} if headway["cv"] < 0.01 else
                                     {"distribution": "lognormal", "mean": h_mean, "cv": min(max(headway["cv"], 0.01), 10.0)})
        item["headway"] = headway
        if amber_extra:
            # o maior tempo de amarelo em que ainda houve cruzamento: um limite inferior do amarelo utilizável
            item["amber_usable"] = {**_stat(amber_extra), "value": max(amber_extra), "pressured_cycles": pressured}
        elif pressured >= MIN_SATURATED_CYCLES:
            item["amber_usable"] = {"value": 0.0, "n": 0, "pressured_cycles": pressured}
        else:
            item["notes"].append("Poucos verdes chegaram ao fim ainda com fila: o amarelo utilizável não pôde ser estimado.")
        out[key] = item
    return out


def aggregate_blocks(blocks: list[dict], block_seconds: float) -> list[dict]:
    """Junta intervalos contíguos em blocos de pelo menos `block_seconds` (o resto curto vai para o último bloco)."""
    groups: list[list[dict]] = []
    current: list[dict] = []
    span = 0.0
    for b in blocks:
        current.append(b)
        span += b["duration"]
        if span >= block_seconds - 1e-9:
            groups.append(current)
            current, span = [], 0.0
    if current:
        if groups and span < block_seconds / 2:
            groups[-1].extend(current)
        else:
            groups.append(current)
    out = []
    for g in groups:
        duration = sum(b["duration"] for b in g)
        arrivals = sum(b["arrivals"] for b in g)
        out.append({"start": g[0]["start"], "duration": duration, "arrivals": arrivals, "lam": arrivals / duration})
    return out


def estimate(
    session: Session, *, max_headway: float = DEFAULT_MAX_HEADWAY, min_run: int = DEFAULT_MIN_RUN,
    core: int = DEFAULT_CORE, profile_block: float = DEFAULT_PROFILE_BLOCK, level: float = 0.95,
) -> dict:
    if not (isinstance(max_headway, Real) and math.isfinite(max_headway) and max_headway > 0):
        raise QueueValidationError("max_headway deve ser um número maior que zero (segundos).", "max_headway")
    if isinstance(min_run, bool) or not isinstance(min_run, int) or min_run < 2:
        raise QueueValidationError("min_run deve ser um inteiro maior ou igual a 2.", "min_run")
    if isinstance(profile_block, bool) or not isinstance(profile_block, Real) or not math.isfinite(profile_block) or profile_block <= 0:
        raise QueueValidationError("profile_block deve ser um número maior que zero (segundos).", "profile_block")
    if isinstance(core, bool) or not isinstance(core, int) or core < min_run:
        raise QueueValidationError("core deve ser um inteiro maior ou igual a min_run.", "core")
    signal = estimate_signal(session)
    arrivals = estimate_arrivals(session, level)
    discharge = estimate_discharge(session, signal, max_headway=max_headway, min_run=min_run, core=core, level=level)
    return {
        "session_id": session.session_id, "horizon": session.horizon, "approach_ids": list(session.approach_ids),
        "method": {"max_headway": max_headway, "min_run": min_run, "core": core, "profile_block": profile_block, "confidence_level": level,
                   "note": ("max_headway, min_run e core são critérios do método (não dados medidos): definem o que conta como "
                            "descarga saturada e quantos veículos da cabeça da fila entram no ajuste.")},
        "signal": signal, "arrivals": arrivals, "discharge": discharge, "notes": session.notes,
        "suggested": suggested_intersection(session, signal, arrivals, discharge, float(profile_block)),
    }


def suggested_intersection(session: Session, signal: dict, arrivals: dict, discharge: dict | None, profile_block: float) -> dict:
    """Corpo no formato da API /simulate; o que não foi estimado vai como null (a tela pede ao usuário).

    O perfil de chegadas junta as contagens em blocos de `profile_block` segundos: usar a contagem de
    cada minuto como taxa de um novo Poisson sortearia a contagem duas vezes e inflaria a variância
    (e, com ela, o atraso). Na validação, as contagens observadas são usadas diretamente.
    """
    approaches = []
    for key in APPROACH_KEYS:
        arr = arrivals[key]
        d = (discharge or {}).get(key) or {}
        approaches.append({
            "name": arr["approach_id"],
            "profile": [{"duration": b["duration"], "lambda": b["lam"]} for b in aggregate_blocks(arr["blocks"], profile_block)],
            "headway": (d.get("headway") or {}).get("suggestion"),
            "first_vehicle_time": (d.get("first_vehicle_time") or {}).get("mean"),
            "amber_usable": (d.get("amber_usable") or {}).get("value"),
            "initial_queue": arr["initial_queue"],
        })
    return {"phases": signal["phases"], "offset": signal["offset"], "approaches": approaches, "simulation_time": session.horizon}
