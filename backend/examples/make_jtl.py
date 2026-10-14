"""Gera CSVs no formato JTL do JMeter a partir de modelos de filas conhecidos.

Serve para testar o recomendador: como se sabe de qual modelo os dados vieram, é possível
conferir se a recomendação acerta. Determinístico para uma mesma semente.

    python -m examples.make_jtl closed --users 20 --think 1.0 --mu 10 --servers 1 > teste.csv
"""

import argparse
import heapq
import random

HEADER = (
    "timeStamp,elapsed,label,responseCode,responseMessage,threadName,dataType,success,"
    "failureMessage,bytes,sentBytes,grpThreads,allThreads,URL,Latency,IdleTime,Connect"
)
T0_MS = 1_760_000_000_000


def _row(start_s: float, elapsed_s: float, ok: bool, users: int, code: str = "200") -> str:
    msg = "OK" if ok else "Service Unavailable"
    return (
        f"{T0_MS + round(start_s * 1000)},{max(round(elapsed_s * 1000), 0)},GET /api,{code},{msg},"
        f"Grupo 1-1,text,{'true' if ok else 'false'},{'' if ok else 'rejeitado'},100,50,{users},{users},"
        f"http://alvo/api,{max(round(elapsed_s * 500), 0)},0,0"
    )


def closed_rows(users: int, think: float, mu: float, servers: int, duration: float,
                seed: int, offset: float = 0.0) -> list[str]:
    """N usuários: pensam ~Exp(Z), pedem, esperam em fila única FIFO, servidores com tempo ~Exp(1/μ)."""
    rng = random.Random(seed)
    free = [0.0] * servers
    heapq.heapify(free)
    pending = [(rng.expovariate(1 / think) if think > 0 else 0.0, u) for u in range(users)]
    heapq.heapify(pending)
    rows = []
    while pending:
        t, u = heapq.heappop(pending)
        if t > duration:
            break
        begin = max(t, heapq.heappop(free))
        done = begin + rng.expovariate(mu)
        heapq.heappush(free, done)
        rows.append((offset + t, done - t, True, users))
        heapq.heappush(pending, (done + (rng.expovariate(1 / think) if think > 0 else 0.0), u))
    return [_row(*r) for r in rows]


def open_rows(lam: float, mu: float, servers: int, capacity: int | None, duration: float,
              seed: int, offset: float = 0.0, users: int = 500) -> list[str]:
    """Chegadas de Poisson, c servidores, capacidade total K (None = infinita). Recusa se cheio."""
    rng = random.Random(seed)
    free = [0.0] * servers
    heapq.heapify(free)
    departures: list[float] = []
    rows, t = [], 0.0
    while True:
        t += rng.expovariate(lam)
        if t > duration:
            break
        while departures and departures[0] <= t:
            heapq.heappop(departures)
        if capacity is not None and len(departures) >= capacity:
            rows.append(_row(offset + t, 0.002, False, users, "503"))
            continue
        begin = max(t, heapq.heappop(free))
        done = begin + rng.expovariate(mu)
        heapq.heappush(free, done)
        heapq.heappush(departures, done)
        rows.append(_row(offset + t, done - t, True, users))
    return rows


def to_csv(rows: list[str]) -> str:
    return "\n".join([HEADER, *rows]) + "\n"


def closed_levels_csv(levels: list[int], think: float, mu: float, servers: int,
                      seconds_per_level: float, seed: int) -> str:
    """Vários patamares de usuários em sequência (como num teste em degraus)."""
    rows, offset = [], 0.0
    for i, users in enumerate(levels):
        rows += closed_rows(users, think, mu, servers, seconds_per_level, seed + i, offset)
        offset += seconds_per_level + 1.0
    return to_csv(rows)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="kind", required=True)
    c = sub.add_parser("closed")
    c.add_argument("--users", type=int, default=20)
    c.add_argument("--think", type=float, default=1.0)
    o = sub.add_parser("open")
    o.add_argument("--lam", type=float, default=8.0)
    o.add_argument("--capacity", type=int, default=None)
    for q in (c, o):
        q.add_argument("--mu", type=float, default=10.0)
        q.add_argument("--servers", type=int, default=1)
        q.add_argument("--duration", type=float, default=300.0)
        q.add_argument("--seed", type=int, default=1)
    a = p.parse_args()
    if a.kind == "closed":
        print(to_csv(closed_rows(a.users, a.think, a.mu, a.servers, a.duration, a.seed)), end="")
    else:
        print(to_csv(open_rows(a.lam, a.mu, a.servers, a.capacity, a.duration, a.seed)), end="")


if __name__ == "__main__":
    main()
