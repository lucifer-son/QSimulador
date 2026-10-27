"""Distribuições do número de clientes e do tempo de espera (Fase 13, RFC-22 e RFC-23).

- P(n): distribuição estacionária do número de clientes no sistema, analítica, para M/M/1, M/M/c,
  M/M/1/K e M/M/c/K. Na fila ilimitada a cauda é infinita: mostra-se até o estado em que a massa
  restante cai abaixo de `TAIL_EPS` (ou do teto de estados) e a massa omitida é informada.
- P(Wq > t): fórmula fechada do M/M/c (inclui o M/M/1, que é c = 1):

      P(Wq > t) = C(c, a) · exp(−(c·μ − λ)·t),   C = Erlang C = P(esperar).

  Os demais modelos (capacidade finita e serviço geral) usam o histograma da simulação, em
  `app.analysis.wait_simulation`.

As funções devolvem estruturas simples (sem NumPy) e não dependem da API.
"""

import math
from dataclasses import asdict, dataclass

import numpy as np
from scipy.special import gammaln

from app.analytical.mmck import _mmc_p0, _stationary_distribution, erlang_b, queue_metrics
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.mmck import validate_mmc_parameters, validate_queue_parameters

TAIL_EPS = 1e-6          # massa que se aceita omitir na cauda da fila ilimitada
MAX_STATES = 500         # teto de estados devolvidos (limita a resposta e o gráfico)
MAX_TAIL_POINTS = 200    # teto de pontos da curva P(Wq > t)
DEFAULT_TAIL_POINTS = 60
TAIL_DISPLAY_EPS = 1e-4  # a curva vai até P(Wq > t) cair a este valor
PERCENTILES = (0.5, 0.9, 0.95, 0.99)

STATE_MODELS = ("mm1", "mmc", "mm1k", "mmck")


@dataclass(frozen=True)
class StateDistribution:
    model: str
    servers: int
    capacity: int | None
    states: list[int]            # n mostrados (em ordem crescente)
    p: list[float]               # P(N = n)
    cumulative: list[float]      # P(N ≤ n), acumulado só sobre os estados mostrados
    omitted_mass: float          # 1 − Σ p dos estados mostrados (cauda ou trechos cortados)
    p0: float
    mean: float                  # L = E[N] exato (não só dos estados mostrados)
    rho: float
    p_wait: float                # P(N ≥ c) na fila ilimitada (Erlang C); chegada aceita que espera nos finitos
    p_block: float               # P(N = K); 0 na fila ilimitada

    def as_dict(self) -> dict:
        return asdict(self)


def _log_unnormalized(n: np.ndarray, a: float, servers: int) -> np.ndarray:
    """log de aⁿ/n! (n ≤ c) e de aⁿ/(c!·c^(n−c)) (n > c)."""
    return (
        n * math.log(a)
        - gammaln(np.minimum(n, servers) + 1)
        - np.maximum(n - servers, 0) * math.log(servers)
    )


def _unbounded_state_distribution(lam: float, mu: float, servers: int) -> tuple[np.ndarray, float, float, float]:
    """P(0..m) do M/M/c, o último estado m mostrado e a massa que sobra além de m."""
    a = lam / mu
    rho = a / servers
    b = erlang_b(a, servers)
    p_wait = b / (1 - rho * (1 - b))                      # = P(N ≥ c), por PASTA
    p0 = _mmc_p0(a, servers, rho)

    # P(N > m) = P(N ≥ c)·ρ^(m + 1 − c) para m ≥ c − 1: exata (a cauda é geométrica).
    if rho * p_wait <= 0 or p_wait <= TAIL_EPS:
        extra = 0
    else:
        extra = max(math.ceil(math.log(TAIL_EPS / p_wait) / math.log(rho)) - 1, 0)
    m = min(max(servers, servers - 1 + extra), MAX_STATES - 1)
    n = np.arange(m + 1)
    p = p0 * np.exp(_log_unnormalized(n, a, servers))
    tail = p_wait * rho ** (m + 1 - servers)
    return p, tail, p_wait, p0


def _window(p: np.ndarray) -> tuple[int, int]:
    """Menor trecho [lo, hi] que guarda quase toda a massa, limitado a MAX_STATES estados."""
    cum = np.cumsum(p)
    lo = int(np.searchsorted(cum, TAIL_EPS / 2, side="right"))
    hi = int(np.searchsorted(cum, 1 - TAIL_EPS / 2, side="left"))
    hi = min(hi, p.size - 1)
    if hi - lo + 1 > MAX_STATES:
        mode = int(np.argmax(p))
        lo = max(0, min(mode - MAX_STATES // 2, p.size - MAX_STATES))
        hi = lo + MAX_STATES - 1
    return lo, hi


def state_distribution(
    model: str, lam: float, mu: float, servers: int = 1, capacity: int | None = None
) -> StateDistribution:
    """P(n) analítica de M/M/1 (`mm1`), M/M/c (`mmc`), M/M/1/K (`mm1k`) ou M/M/c/K (`mmck`).

    Levanta QueueValidationError para parâmetros inválidos (e UnstableSystemError se λ ≥ c·μ
    na fila ilimitada), ou se o modelo não tem P(n) analítica (serviço geral e Erlang-B).
    """
    if model not in STATE_MODELS:
        raise QueueValidationError(
            f"P(n) analítica existe só para: {', '.join(STATE_MODELS)}. "
            "O serviço geral (M/G/c) não tem P(n) fechada: a aproximação de Allen–Cunneen só define as médias.",
            "model",
        )
    if model in ("mm1", "mm1k"):
        servers = 1
    if model in ("mm1", "mmc"):
        capacity = None
    elif capacity is None:
        raise QueueValidationError("capacity é obrigatório nos modelos de capacidade finita.", "capacity")

    lam, mu, servers, capacity = validate_queue_parameters(lam, mu, servers, capacity)
    metrics = queue_metrics(lam, mu, servers, capacity)

    if capacity is None:
        p_all, tail, p_wait, p0 = _unbounded_state_distribution(lam, mu, servers)
        states = np.arange(p_all.size)
        p = p_all
        omitted = float(tail)
    else:
        p_all = _stationary_distribution(lam, mu, servers, capacity)
        lo, hi = _window(p_all)
        states = np.arange(lo, hi + 1)
        p = p_all[lo:hi + 1]
        omitted = float(max(1.0 - p.sum(), 0.0)) if (lo > 0 or hi < capacity) else 0.0
        p_wait = metrics.p_wait
        p0 = float(p_all[0])

    return StateDistribution(
        model=model, servers=servers, capacity=capacity,
        states=[int(s) for s in states], p=[float(x) for x in p],
        cumulative=[float(x) for x in np.cumsum(p)], omitted_mass=omitted,
        p0=float(p0), mean=float(metrics.L), rho=float(metrics.rho),
        p_wait=float(p_wait), p_block=float(metrics.p_block),
    )


# ---------- P(Wq > t) ----------

@dataclass(frozen=True)
class WaitTail:
    """P(Wq > t) do M/M/c por fórmula fechada."""

    model: str
    servers: int
    t: list[float]
    survival: list[float]        # P(Wq > t)
    p_wait: float                # P(Wq > 0) = Erlang C
    decay_rate: float            # c·μ − λ: a cauda cai como exp(−decay_rate·t)
    mean_wait: float             # Wq
    percentiles: dict[str, float]   # tempo de espera que não é excedido em p % dos clientes

    def as_dict(self) -> dict:
        return asdict(self)


def wait_survival_mmc(lam: float, mu: float, servers: int, t: float | np.ndarray) -> float | np.ndarray:
    """P(Wq > t) = C·exp(−(c·μ − λ)·t), t ≥ 0. Exige λ < c·μ."""
    lam, mu, c = validate_mmc_parameters(lam, mu, servers)
    a = lam / mu
    rho = a / c
    b = erlang_b(a, c)
    p_wait = b / (1 - rho * (1 - b))
    return p_wait * np.exp(-(c * mu - lam) * np.asarray(t, dtype=float)) if not np.isscalar(t) \
        else float(p_wait * math.exp(-(c * mu - lam) * t))


def wait_percentile_mmc(p_wait: float, decay_rate: float, q: float) -> float:
    """Menor t com P(Wq ≤ t) ≥ q. É 0 quando a fração que não espera já cobre q."""
    if q <= 1 - p_wait:
        return 0.0
    return math.log(p_wait / (1 - q)) / decay_rate


def validate_points(points: object) -> int:
    if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= MAX_TAIL_POINTS:
        raise QueueValidationError(f"points deve ser um inteiro entre 2 e {MAX_TAIL_POINTS}.", "points")
    return points


def wait_tail_mmc(
    model: str, lam: float, mu: float, servers: int = 1, points: int = DEFAULT_TAIL_POINTS,
    t_max: float | None = None,
) -> WaitTail:
    """Curva P(Wq > t) do M/M/1 (`mm1`) ou M/M/c (`mmc`), de t = 0 até a cauda ficar desprezível."""
    if model not in ("mm1", "mmc"):
        raise QueueValidationError("A fórmula fechada de P(Wq > t) é a do M/M/c (`mm1` ou `mmc`).", "model")
    if model == "mm1":
        servers = 1
    lam, mu, c = validate_mmc_parameters(lam, mu, servers)
    points = validate_points(points)

    a = lam / mu
    rho = a / c
    b = erlang_b(a, c)
    p_wait = b / (1 - rho * (1 - b))
    theta = c * mu - lam
    if t_max is None:
        t_max = max(math.log(p_wait / TAIL_DISPLAY_EPS), 3.0) / theta if p_wait > 0 else 3.0 / theta
    elif isinstance(t_max, bool) or not isinstance(t_max, (int, float)) or not math.isfinite(t_max) or t_max <= 0:
        raise QueueValidationError("t_max deve ser um número positivo.", "t_max")

    t = np.linspace(0.0, float(t_max), points)
    survival = p_wait * np.exp(-theta * t)
    percentiles = {f"p{round(q * 100)}": wait_percentile_mmc(p_wait, theta, q) for q in PERCENTILES}
    return WaitTail(
        model=model, servers=c, t=[float(x) for x in t], survival=[float(x) for x in survival],
        p_wait=float(p_wait), decay_rate=float(theta),
        mean_wait=float(p_wait / theta), percentiles={k: float(v) for k, v in percentiles.items()},
    )
