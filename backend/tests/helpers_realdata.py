"""CSVs sintéticos de resposta conhecida e um gerador de rastro de sistema fechado independente do simulador."""

import heapq

import numpy as np

HEADER = "timeStamp,elapsed,label,responseCode,success,allThreads"


def jmeter_csv(rows, header=HEADER):
    """rows: iteráveis (timeStamp_ms, elapsed_ms, label, success[, allThreads])."""
    lines = [header]
    for r in rows:
        ts, el, label, ok, *rest = r
        threads = rest[0] if rest else 5
        lines.append(f"{ts},{el},{label},200,{'true' if ok else 'false'},{threads}")
    return "\n".join(lines) + "\n"


def regular_rows(n=100, gap_ms=100, elapsed_ms=100, label="home", t0=1_700_000_000_000, threads=5):
    """n amostras, uma a cada gap_ms, todas com a mesma duração: vazão e média exatas."""
    return [(t0 + k * gap_ms, elapsed_ms, label, True, threads) for k in range(n)]


def closed_trace_rows(users, think, mu, duration, seed, t0=1_700_000_000_000):
    """Rastro de um sistema fechado de 1 servidor FIFO, escrito à mão (independente do SimPy)."""
    rng = np.random.default_rng(seed)
    heap = [(rng.exponential(think), u) for u in range(users)]
    heapq.heapify(heap)
    free_at, rows = 0.0, []
    while heap:
        arrival, u = heapq.heappop(heap)
        if arrival > duration:
            break
        start = max(arrival, free_at)
        end = start + rng.exponential(1.0 / mu)
        free_at = end
        rows.append((t0 + int(arrival * 1000), max(int(round((end - arrival) * 1000)), 1), "req", True, users))
        heapq.heappush(heap, (end + rng.exponential(think), u))
    return rows
