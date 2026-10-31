"""Motor do cruzamento semaforizado (Fase 13.1).

Cada aproximação é uma fila FIFO atendida só durante o seu verde. Como a fila é FIFO e o ciclo é
fixo, o instante em que cada veículo cruza a linha de retenção sai de uma recursão por veículo
(exata, sem fila de eventos):

    pronto_k = max(chegada_k, saída_{k-1} + h_{k-1})

onde h_k é o intervalo que o veículo k deixa a linha ocupada depois de cruzar (o "tempo de serviço"
da linha de retenção, como no M/G/1 da Fase 9), e, se `pronto_k` cai fora da janela de descarga, o veículo cruza no início da descarga do próximo
verde (início do verde + ℓ, o tempo até o 1º veículo da fila cruzar). A janela de descarga de cada ciclo é
[início do verde + ℓ, fim do verde + amarelo utilizável].

Regra do veículo que não enfrenta fila: quem chega com o verde aberto, sem ninguém à frente
(`pronto = chegada`), cruza na hora, mesmo nos ℓ primeiros segundos (não há partida parada).
Quem esteve na fila (esperou o verde ou foi limitado pelo intervalo h) só cruza a partir de ℓ.

Números aleatórios comuns: cada aproximação tem dois fluxos independentes, um para as chegadas
(exponenciais padrão, convertidas pela inversa da intensidade acumulada) e outro para os
intervalos de descarga h_k. Planos diferentes com a mesma semente enfrentam as mesmas chegadas
e os mesmos intervalos (o k-ésimo veículo é o mesmo em todos).
"""

import math
from dataclasses import dataclass

import numpy as np

from app.traffic.plan import ArrivalProfile, Intersection

FREE_EPS = 1e-9


@dataclass(frozen=True)
class ApproachRun:
    """Resultado bruto de uma aproximação em uma réplica."""

    arrivals: np.ndarray      # instantes de chegada, ordenados (os n0 iniciais valem 0)
    departures: np.ndarray    # instantes em que cruzam a linha de retenção (não decrescentes)
    n_initial: int            # os n0 primeiros veículos já estavam na fila em t = 0


def streams(seed: int, replication: int) -> tuple[np.random.Generator, ...]:
    """Quatro fluxos independentes da réplica: chegadas 1 e 2, intervalos 1 e 2."""
    children = np.random.SeedSequence([seed, replication]).spawn(4)
    return tuple(np.random.default_rng(child) for child in children)


def sample_arrivals(profile: ArrivalProfile, horizon: float, rng: np.random.Generator) -> np.ndarray:
    """Chegadas de um Poisson (não homogêneo, com taxa constante por blocos) em [0, horizon)."""
    if profile.counts is not None:
        return _arrivals_given_counts(profile, horizon, rng)
    total = profile.expected_arrivals(horizon)
    if total <= 0:
        return np.empty(0)
    size = int(total + 6.0 * math.sqrt(total) + 16)
    cum_exp = np.cumsum(rng.standard_exponential(size))
    while cum_exp[-1] < total:                       # raro: amostra curta demais, estende
        cum_exp = np.concatenate([cum_exp, cum_exp[-1] + np.cumsum(rng.standard_exponential(size))])
    cum_exp = cum_exp[cum_exp < total]
    if profile.constant:
        return cum_exp / profile.rates[0]
    starts = np.asarray(profile.starts)
    rates = np.asarray(profile.rates)
    widths = np.diff(np.append(starts, math.inf))
    cum_start = np.concatenate([[0.0], np.cumsum(rates[:-1] * widths[:-1])])
    block = np.searchsorted(cum_start, cum_exp, side="right") - 1
    return starts[block] + (cum_exp - cum_start[block]) / rates[block]


def _arrivals_given_counts(profile: ArrivalProfile, horizon: float, rng: np.random.Generator) -> np.ndarray:
    """Chegadas condicionadas às contagens: N_j veículos por bloco, com instantes uniformes dentro do bloco.

    É o que reproduz uma gravação: o número de chegadas de cada intervalo é o observado (nada é
    sorteado de novo) e só o instante exato dentro do intervalo é desconhecido.
    """
    starts = np.asarray(profile.starts)
    ends = np.append(starts[1:], profile.end)
    counts = np.asarray(profile.counts, dtype=int)
    u = rng.random(int(counts.sum()))
    out, pos = [], 0
    for start, end, n in zip(starts, ends, counts):
        out.append(np.sort(start + (end - start) * u[pos:pos + n]))
        pos += n
    arrivals = np.concatenate(out) if out else np.empty(0)
    return arrivals[arrivals < horizon]


def discharge(
    arrivals: np.ndarray, headways: np.ndarray, n_initial: int, *,
    green_start: float, green: float, amber_usable: float, lost: float, cycle: float,
) -> np.ndarray:
    """Instante em que cada veículo cruza a linha de retenção (recursão por veículo, FIFO)."""
    n = len(arrivals)
    deps = np.empty(n)
    window = green + amber_usable            # a janela [gs, gs + window] está aberta
    prev_plus_h = -math.inf
    floor = math.floor
    arr_list = arrivals.tolist()
    head_list = headways.tolist()
    for k in range(n):
        arr = arr_list[k]
        if arr >= prev_plus_h:
            t = arr
            queued = k < n_initial           # fila inicial: já esperava em t = 0
        else:
            t = prev_plus_h
            queued = True
        cycle_index = floor((t - green_start) / cycle)
        gs = green_start + cycle_index * cycle
        r = t - gs
        if r <= window:
            dep = t if (r >= lost or not queued) else gs + lost
        else:
            dep = gs + cycle + lost
        deps[k] = dep
        prev_plus_h = dep + head_list[k]
    return deps


def simulate_approach(
    inter: Intersection, index: int, horizon: float,
    rng_arrivals: np.random.Generator, rng_headways: np.random.Generator,
) -> ApproachRun:
    app = inter.approaches[index]
    phase = inter.signal.phases[index]
    external = sample_arrivals(app.profile, horizon, rng_arrivals)
    arrivals = np.concatenate([np.zeros(app.initial_queue), external])
    headways = app.headway.sample(rng_headways, len(arrivals)) if len(arrivals) else np.empty(0)
    deps = discharge(
        arrivals, headways, app.initial_queue,
        green_start=inter.signal.green_start(index), green=phase.green,
        amber_usable=app.amber_usable, lost=app.first_vehicle_time, cycle=inter.signal.cycle,
    )
    return ApproachRun(arrivals, deps, app.initial_queue)


def simulate_replication(inter: Intersection, horizon: float, seed: int, replication: int) -> tuple[ApproachRun, ApproachRun]:
    a1, a2, h1, h2 = streams(seed, replication)
    return (
        simulate_approach(inter, 0, horizon, a1, h1),
        simulate_approach(inter, 1, horizon, a2, h2),
    )
