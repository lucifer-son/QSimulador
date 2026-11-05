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

ℓ variável: com `first_vehicle_cv` > 0, cada verde (índice de ciclo) tem o seu ℓ, lognormal em torno de ℓ, de um
quarto fluxo por aproximação (também separado dos outros). Planos diferentes veem a mesma sequência de ℓ por índice de ciclo.

Classes de veículos: um terceiro fluxo por aproximação, separado dos outros (por isso as sementes
sem classes seguem dando os mesmos resultados de antes), sorteia a classe de cada veículo. O
intervalo que o veículo deixa a linha ocupada é h_k · fator da classe. Na reprodução de uma sessão
com contagens por classe, o nº de chegadas de cada classe em cada intervalo é o observado.
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
    factors: np.ndarray | None = None      # carros equivalentes de cada veículo (None = todos valem 1)
    classes: np.ndarray | None = None      # índice da classe de cada veículo (None = sem classes)


def streams(seed: int, replication: int, n: int = 2) -> tuple[np.random.Generator, ...]:
    """2n fluxos independentes da réplica: chegadas de cada aproximação e depois os intervalos de cada uma."""
    children = np.random.SeedSequence([seed, replication]).spawn(2 * n)
    return tuple(np.random.default_rng(child) for child in children)


def class_streams(seed: int, replication: int, n: int) -> tuple[np.random.Generator, ...]:
    """Um fluxo por aproximação para sortear a classe dos veículos (independente dos demais)."""
    children = np.random.SeedSequence([seed, replication, 7919]).spawn(n)
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


def lost_streams(seed: int, replication: int, n: int) -> tuple[np.random.Generator, ...]:
    """Um fluxo por aproximação para o ℓ de cada ciclo (usado só se `first_vehicle_cv` > 0)."""
    children = np.random.SeedSequence([seed, replication, 6151]).spawn(n)
    return tuple(np.random.default_rng(child) for child in children)


class _CycleLost:
    """ℓ de cada ciclo, sorteado sob demanda (a fila de uma aproximação saturada pode ir muito além do horizonte)."""

    def __init__(self, mean: float, cv: float, rng: np.random.Generator, base: int) -> None:
        sigma2 = math.log1p(cv * cv)
        self._mu, self._sigma = math.log(mean) - sigma2 / 2, math.sqrt(sigma2)
        self._rng, self._base, self._values = rng, base, []

    def __call__(self, index: int) -> float:
        need = index - self._base + 1
        while len(self._values) < need:
            self._values.extend(np.exp(self._mu + self._sigma * self._rng.standard_normal(256)).tolist())
        return self._values[index - self._base]


def _arrivals_given_class_counts(
    profile: ArrivalProfile, horizon: float, rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Chegadas condicionadas às contagens por classe: (instantes ordenados, índice da classe de cada um)."""
    starts = np.asarray(profile.starts)
    ends = np.append(starts[1:], profile.end)
    table = np.asarray(profile.class_counts, dtype=int)           # blocos × classes
    u = rng.random(int(table.sum()))
    times, labels, pos = [], [], 0
    for start, end, row in zip(starts, ends, table):
        for c, n in enumerate(row):
            times.append(start + (end - start) * u[pos:pos + n])
            labels.append(np.full(int(n), c, dtype=int))
            pos += int(n)
    if not times:
        return np.empty(0), np.empty(0, dtype=int)
    t, c = np.concatenate(times), np.concatenate(labels)
    order = np.lexsort((c, t))
    t, c = t[order], c[order]
    keep = t < horizon
    return t[keep], c[keep]


def discharge(
    arrivals: np.ndarray, headways: np.ndarray, n_initial: int, *,
    green_start: float, green: float, amber_usable: float, lost: float, cycle: float,
    lost_of: "_CycleLost | None" = None,
) -> np.ndarray:
    """Instante em que cada veículo cruza a linha de retenção (recursão por veículo, FIFO).

    `lost_of(índice do ciclo)` dá o ℓ de cada verde quando ele varia; sem ele, `lost` vale para todos."""
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
        if lost_of is None:
            ell, ell_next = lost, lost
        else:
            ell, ell_next = lost_of(cycle_index), lost_of(cycle_index + 1)
        if r <= window:
            dep = t if (r >= ell or not queued) else gs + ell
        else:
            dep = gs + cycle + ell_next
        deps[k] = dep
        prev_plus_h = dep + head_list[k]
    return deps


def simulate_approach(
    inter: Intersection, index: int, horizon: float,
    rng_arrivals: np.random.Generator, rng_headways: np.random.Generator,
    rng_classes: np.random.Generator | None = None, rng_lost: np.random.Generator | None = None,
) -> ApproachRun:
    app = inter.approaches[index]
    phase = inter.signal.phases[index]
    classes = factors = None
    if app.classes:
        if rng_classes is None:
            rng_classes = np.random.default_rng(0)
        shares = np.asarray([c.share for c in app.classes], dtype=float)
        factor_of = np.asarray([c.factor for c in app.classes], dtype=float)
        initial_cls = rng_classes.choice(len(app.classes), size=app.initial_queue, p=shares) if app.initial_queue else np.empty(0, dtype=int)
        if app.profile.class_counts is not None:
            external, external_cls = _arrivals_given_class_counts(app.profile, horizon, rng_arrivals)
        else:
            external = sample_arrivals(app.profile, horizon, rng_arrivals)
            external_cls = rng_classes.choice(len(app.classes), size=len(external), p=shares) if len(external) else np.empty(0, dtype=int)
        classes = np.concatenate([initial_cls, external_cls]).astype(int)
        factors = factor_of[classes] if len(classes) else np.empty(0)
    else:
        external = sample_arrivals(app.profile, horizon, rng_arrivals)
    arrivals = np.concatenate([np.zeros(app.initial_queue), external])
    headways = app.headway.sample(rng_headways, len(arrivals)) if len(arrivals) else np.empty(0)
    if factors is not None and len(headways):
        headways = headways * factors
    lost_of = None
    if app.first_vehicle_cv > 0 and app.first_vehicle_time > 0:
        base = math.floor((0.0 - inter.signal.green_start(index)) / inter.signal.cycle)
        lost_of = _CycleLost(app.first_vehicle_time, app.first_vehicle_cv, rng_lost or np.random.default_rng(0), base)
    deps = discharge(
        arrivals, headways, app.initial_queue,
        green_start=inter.signal.green_start(index), green=phase.green, lost_of=lost_of,
        amber_usable=app.amber_usable, lost=app.first_vehicle_time, cycle=inter.signal.cycle,
    )
    return ApproachRun(arrivals, deps, app.initial_queue, factors, classes)


def simulate_replication(inter: Intersection, horizon: float, seed: int, replication: int) -> tuple[ApproachRun, ...]:
    n = len(inter.approaches)
    flows = streams(seed, replication, n)
    cls = class_streams(seed, replication, n)
    lost = lost_streams(seed, replication, n)
    return tuple(simulate_approach(inter, i, horizon, flows[i], flows[n + i], cls[i], lost[i]) for i in range(n))
