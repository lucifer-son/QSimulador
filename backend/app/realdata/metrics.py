"""Métricas empíricas de um teste de carga, calculadas sobre uma janela de tempo.

Definições (todas em segundos e req/s):
- λ̂ (arrival_rate): amostras **iniciadas** na janela / duração (inclui as rejeitadas).
- X̂ (throughput): amostras concluídas **com sucesso** na janela / duração.
- W̄: média de `elapsed` das amostras iniciadas na janela e bem-sucedidas.
- L̂: requisições em andamento, em média no tempo (sobreposição exata dos intervalos
  [início, fim] com a janela). Pela lei de Little vale L̂ ≈ X̂·W̄; serve para conferir a
  janela, não como validação independente.
- N̄: usuários ativos (`allThreads`), ponderados pelo tempo.
- Ẑ: tempo de reflexão, N̄/X̂ − W̄ (lei do tempo de resposta interativo).
- p̂_block: rejeições / amostras iniciadas. Rejeição = o servidor recusou ou desviou a
  requisição (429, 502, 503, 504, conexão recusada); erros funcionais ficam à parte.
"""

import re
from dataclasses import asdict, dataclass

import numpy as np
from scipy import stats

from app.realdata.jmeter import JMeterDataset
from app.simulation.results import MetricSummary

REJECTION_CODES = frozenset({"429", "502", "503", "504"})
_REJECTION_TEXT = re.compile(r"refused|connection reset|too many requests|service unavailable", re.I)
BATCHES = 20
MS_TOLERANCE = 0.0015  # timeStamp e elapsed são arredondados a 1 ms; um término até 1,5 ms depois já conta como ocorrido


def rejection_mask(ds: JMeterDataset) -> np.ndarray:
    """Falhas que indicam fila cheia ou servidor recusando carga (não erro de aplicação)."""
    failed = ~ds.success
    mask = np.zeros(len(ds), dtype=bool)
    if ds.response_code is not None:
        mask |= np.isin(ds.response_code, list(REJECTION_CODES))
        mask |= np.array([bool(_REJECTION_TEXT.search(str(c))) for c in ds.response_code])
    for text in (ds.response_message, ds.failure_message):
        if text is not None:
            mask |= np.array([bool(_REJECTION_TEXT.search(str(t))) for t in text])
    return mask & failed


def trimmed_window(ds: JMeterDataset, trim_start_pct: float = 10.0, trim_end_pct: float = 10.0) -> tuple[float, float]:
    """Janela estável: descarta uma fração do início (aquecimento) e do fim (encerramento)."""
    first, last = float(ds.start[0]), float(ds.start[-1])
    span = last - first
    return first + span * trim_start_pct / 100.0, last - span * trim_end_pct / 100.0


@dataclass(frozen=True)
class EmpiricalMetrics:
    window_start: float
    window_end: float
    duration: float
    samples: int
    successes: int
    rejections: int
    other_failures: int
    arrival_rate: float
    throughput: float
    mean_response: float
    p50: float
    p90: float
    p95: float
    p99: float
    mean_in_flight: float
    peak_in_flight: int
    mean_users: float | None
    think_time: float | None
    p_block: float
    p_error: float
    arrival_cv: float | None
    response_cv: float | None
    # Resumos por lotes de tempo (com IC), no formato da simulação.
    summaries: dict[str, MetricSummary]

    def as_dict(self) -> dict:
        return asdict(self)


def _summary(values: list[float], level: float) -> MetricSummary:
    n = len(values)
    arr = np.asarray(values, dtype=float)
    mean = float(arr.mean()) if n else float("nan")
    if n < 2:
        return MetricSummary(mean=mean, std=None, ci_low=None, ci_high=None, n=n)
    std = float(arr.std(ddof=1))
    half = float(stats.t.ppf((1 + level) / 2, n - 1)) * std / np.sqrt(n)
    return MetricSummary(mean=mean, std=std, ci_low=mean - half, ci_high=mean + half, n=n)


def _overlap(start: np.ndarray, end: np.ndarray, t0: float, t1: float) -> float:
    return float(np.clip(np.minimum(end, t1) - np.maximum(start, t0), 0, None).sum())


def _concurrency_seen(start: np.ndarray, end: np.ndarray, probes: np.ndarray) -> int:
    """Concorrência vista pelas requisições aceitas ao iniciar (inclui a própria), no percentil 99,9.

    O máximo exato é sensível a arredondamentos de 1 ms em `timeStamp` e `elapsed`; o percentil não é.
    """
    if probes.size == 0:
        return 0
    seen = (np.searchsorted(np.sort(start), probes, side="right")
            - np.searchsorted(np.sort(end), probes + MS_TOLERANCE, side="right"))
    return int(round(float(np.percentile(seen, 99.9))))


def _cv(values: np.ndarray) -> float | None:
    if values.size < 30 or values.mean() <= 0:
        return None
    return float(values.std(ddof=1) / values.mean())


def _mean_users(ds: JMeterDataset, t0: float, t1: float) -> float | None:
    """allThreads é registrado quando a amostra termina: média em degraus, ponderada pelo tempo."""
    if ds.all_threads is None:
        return None
    end = ds.end
    sel = (end >= t0) & (end <= t1)
    if sel.sum() == 0:
        return None
    order = np.argsort(end[sel], kind="stable")
    times, users = end[sel][order], ds.all_threads[sel][order].astype(float)
    if times.size == 1:
        return float(users[0])
    gaps = np.diff(times)
    weights = np.append(gaps, gaps.mean())
    if weights.sum() <= 0:
        return float(users.mean())
    return float(np.average(users, weights=weights))


def compute_metrics(
    ds: JMeterDataset, t0: float, t1: float, confidence_level: float = 0.95
) -> EmpiricalMetrics:
    """Métricas empíricas na janela [t0, t1]. Exige ao menos uma amostra bem-sucedida."""
    duration = t1 - t0
    if duration <= 0:
        raise ValueError("A janela precisa ter duração positiva.")

    start, end, elapsed = ds.start, ds.end, ds.elapsed
    started = (start >= t0) & (start <= t1)
    rej = rejection_mask(ds)
    ok = ds.success
    started_ok = started & ok
    completed_ok = ok & (end >= t0) & (end <= t1)

    n_started = int(started.sum())
    resp = elapsed[started_ok]
    mean_w = float(resp.mean()) if resp.size else float("nan")
    x = float(completed_ok.sum()) / duration
    users = _mean_users(ds, t0, t1)
    z = None if users is None or x <= 0 else max(users / x - mean_w, 0.0)

    # Só as aceitas: as rejeitadas voltam em milissegundos e não ocupam o sistema.
    peak = _concurrency_seen(start[ok], end[ok], start[started_ok])
    gaps = np.diff(start[started])

    # Lotes de tempo iguais para o IC (média de lotes).
    edges = np.linspace(t0, t1, BATCHES + 1)
    w_batches, x_batches, lam_batches = [], [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        in_b = (start >= lo) & (start < hi) & ok
        done_b = ok & (end >= lo) & (end < hi)
        lam_batches.append(float(((start >= lo) & (start < hi)).sum()) / (hi - lo))
        x_batches.append(float(done_b.sum()) / (hi - lo))
        if in_b.any():
            w_batches.append(float(elapsed[in_b].mean()))

    percentiles = np.percentile(resp, [50, 90, 95, 99]) if resp.size else [float("nan")] * 4
    return EmpiricalMetrics(
        window_start=t0, window_end=t1, duration=duration, samples=n_started,
        successes=int(started_ok.sum()), rejections=int((started & rej).sum()),
        other_failures=int((started & ~ok & ~rej).sum()),
        arrival_rate=n_started / duration, throughput=x, mean_response=mean_w,
        p50=float(percentiles[0]), p90=float(percentiles[1]),
        p95=float(percentiles[2]), p99=float(percentiles[3]),
        mean_in_flight=_overlap(start, end, t0, t1) / duration, peak_in_flight=peak,
        mean_users=users, think_time=z,
        p_block=float((started & rej).sum()) / n_started if n_started else 0.0,
        p_error=float((started & ~ok & ~rej).sum()) / n_started if n_started else 0.0,
        arrival_cv=_cv(gaps), response_cv=_cv(resp),
        summaries={
            "W": _summary(w_batches, confidence_level),
            "throughput": _summary(x_batches, confidence_level),
            "arrival_rate": _summary(lam_batches, confidence_level),
        },
    )


@dataclass(frozen=True)
class LoadLevel:
    """Um patamar de carga (usuários constantes) com as métricas da sua janela estável."""

    users: int | None
    metrics: EmpiricalMetrics


MIN_LEVEL_SAMPLES = 30
MIN_LEVEL_SECONDS = 1.0


def split_levels(
    ds: JMeterDataset, trim_start_pct: float = 10.0, trim_end_pct: float = 10.0,
    confidence_level: float = 0.95,
) -> list[LoadLevel]:
    """Divide o teste em patamares de `allThreads` constante, do menor para o maior.

    Sem a coluna `allThreads`, ou sem nenhum patamar longo o bastante, devolve um único
    nível sobre a janela inteira (com `users` = N̄ arredondado, se houver a coluna).
    """
    levels: list[LoadLevel] = []
    if ds.all_threads is not None:
        values = ds.all_threads
        boundaries = np.flatnonzero(np.diff(values) != 0) + 1
        runs = np.split(np.arange(len(values)), boundaries)
        best: dict[int, tuple[float, float, float]] = {}  # users -> (duração, início, fim)
        for run in runs:
            t_a, t_b = float(ds.start[run[0]]), float(ds.start[run[-1]])
            if run.size < MIN_LEVEL_SAMPLES or t_b - t_a < MIN_LEVEL_SECONDS:
                continue
            n = int(values[run[0]])
            if n not in best or (t_b - t_a) > best[n][0]:
                best[n] = (t_b - t_a, t_a, t_b)
        for n, (span, t_a, t_b) in sorted(best.items()):
            lo, hi = t_a + span * trim_start_pct / 100, t_b - span * trim_end_pct / 100
            if hi > lo:
                levels.append(LoadLevel(n, compute_metrics(ds, lo, hi, confidence_level)))
    if levels:
        return levels

    lo, hi = trimmed_window(ds, trim_start_pct, trim_end_pct)
    whole = compute_metrics(ds, lo, hi, confidence_level)
    users = None if whole.mean_users is None else max(1, round(whole.mean_users))
    return [LoadLevel(users, whole)]


def response_trend(ds: JMeterDataset, t0: float, t1: float) -> float | None:
    """Crescimento relativo do tempo de resposta ao longo da janela (reta ajustada), ou 0 sem evidência.

    Regressão linear sobre as médias de 20 lotes de tempo. Só conta como tendência se a inclinação for
    significativa (p < 0,01): comparar o início com o fim da janela confunde a oscilação natural de uma
    fila estável (autocorrelação) com fila crescendo. Devolve None se a janela tem poucos dados.
    """
    edges = np.linspace(t0, t1, BATCHES + 1)
    mids, means = [], []
    for lo, hi in zip(edges[:-1], edges[1:]):
        sel = ds.success & (ds.start >= lo) & (ds.start < hi)
        if sel.sum() >= 3:
            mids.append((lo + hi) / 2)
            means.append(float(ds.elapsed[sel].mean()))
    if len(mids) < 10:
        return None
    fit = stats.linregress(mids, means)
    if not np.isfinite(fit.pvalue) or fit.pvalue >= 0.01 or fit.slope <= 0:
        return 0.0
    at_start = fit.intercept + fit.slope * t0
    return float(fit.slope * (t1 - t0) / at_start) if at_start > 0 else float("inf")
