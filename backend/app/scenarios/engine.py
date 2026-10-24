"""Simulação de um cenário com números aleatórios comuns (CRN).

Cada réplica recebe dois fluxos independentes, derivados da semente: um só para as chegadas e
outro só para os serviços. Todos os cenários usam as mesmas sementes e, na réplica r, os mesmos
dois fluxos. O k-ésimo intervalo entre chegadas e o serviço do cliente k saem do mesmo sorteio
em qualquer cenário; só mudam de escala quando λ ou μ mudam. Mudar λ, μ, c ou K altera a ordem
dos eventos, mas não desloca os sorteios, e é isso que mantém os cenários correlacionados.

Por isso o serviço é sorteado na chegada, por número do cliente (e não no início do
atendimento): com K finito, clientes recusados deslocariam os sorteios dos seguintes. Os blocos
de sorteios são de tamanho fixo, então o valor k não depende de quantos sorteios foram usados.

Este módulo só é usado na comparação de cenários. As simulações das fases anteriores seguem com
um único gerador por réplica, e os resultados delas não mudam.
"""

from collections.abc import Callable

import numpy as np

from app.domain.validation.errors import InsufficientSampleError
from app.scenarios.spec import Resolved
from app.simulation.mmck import run_replication
from app.simulation.results import QueueReplicationResult
from app.simulation.stats import summarize
from app.simulation.results import MetricSummary

_BLOCK = 2048


def exponential_stream(rng: np.random.Generator, rate: float) -> Callable[[], float]:
    """Intervalos entre chegadas: o k-ésimo é Z_k/λ, com Z_k padrão do fluxo (a escala é só 1/λ)."""
    state = {"buf": np.empty(0), "i": 0}

    def next_value() -> float:
        if state["i"] >= len(state["buf"]):
            state["buf"] = rng.standard_exponential(_BLOCK)
            state["i"] = 0
        value = float(state["buf"][state["i"]]) / rate
        state["i"] += 1
        return value

    return next_value


def replication_streams(seed: int, replications: int) -> list[tuple[np.random.Generator, np.random.Generator]]:
    """(fluxo de chegadas, fluxo de serviços) de cada réplica; os mesmos para qualquer cenário."""
    streams = []
    for child in np.random.SeedSequence(seed).spawn(replications):
        arrivals, services = child.spawn(2)
        streams.append((np.random.default_rng(arrivals), np.random.default_rng(services)))
    return streams


def simulate_runs(
    scenario: Resolved, simulation_time: float, warmup_time: float, replications: int, seed: int,
) -> tuple[QueueReplicationResult, ...]:
    """R réplicas do cenário com fluxos separados de chegada e serviço, derivados de `seed`.

    Não valida (a comparação valida tudo antes de simular). Levanta InsufficientSampleError se
    alguma réplica terminar sem clientes suficientes para estimar as métricas.
    """
    runs = []
    for index, (arrival_rng, service_rng) in enumerate(replication_streams(seed, replications)):
        runs.append(run_replication(
            scenario.lam, scenario.service.mu, scenario.servers, scenario.sim_capacity,
            simulation_time, warmup_time, arrival_rng, index=index,
            interarrival=exponential_stream(arrival_rng, scenario.lam),
            service_at_arrival=scenario.service.sampler(service_rng),
        ))
    if any(run.measured_customers == 0 for run in runs):
        raise InsufficientSampleError(
            "A simulação terminou sem clientes suficientes para estimar as métricas. "
            "Aumente simulation_time.",
            field="simulation_time",
        )
    return tuple(runs)


def summarize_runs(
    runs: tuple[QueueReplicationResult, ...], metrics: tuple[str, ...], confidence_level: float,
) -> dict[str, MetricSummary]:
    return {name: summarize([getattr(r, name) for r in runs], confidence_level) for name in metrics}
