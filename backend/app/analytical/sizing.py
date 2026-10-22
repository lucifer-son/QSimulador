"""Dimensionamento: nível de serviço e custo em função do número de servidores (Fase 11).

É uma camada de decisão sobre os modelos que já existem. Para cada número de servidores c, calcula
as métricas do modelo e, opcionalmente, o nível de serviço P(Wq ≤ t) e o custo

    C(c) = c·hₛ + λ_ef·Wq·hₑ + λ·B·h_perda

em que λ_ef = λ·(1 − B) é a vazão (os clientes recusados não esperam) e B é o bloqueio (0 sem perda).
As unidades de tempo são as de λ e μ: t, hₛ, hₑ e h_perda devem usar a mesma.

Famílias dimensionáveis (o M/M/1, o M/M/1/K e o M/G/1 são o caso c = 1 da respectiva família):

- `mmc`: M/M/c. P(Wq > t) = C(c, a)·e^(−(cμ−λ)t), exato.
- `mmck`: M/M/c/K. Exato para quem entra no sistema: um cliente aceito que encontra n ≥ c clientes
  espera n − c + 1 términos, a taxa cμ (soma de fases de Erlang), ponderado por pₙ/(1 − p_K).
- `erlangb`: não há espera; a meta é o bloqueio.
- `mgc`: não há fórmula exata. Usa a cauda exponencial P(Wq > t) ≈ P(esperar)·e^(−t·P(esperar)/Wq),
  que é exata com CV = 1 (Wq = C/(cμ−λ)). É uma aproximação, marcada como tal.
"""

from dataclasses import dataclass

import numpy as np
from scipy.stats import gamma

from app.analytical.erlangb import erlangb_metrics
from app.analytical.mgc import mgc_metrics, validity_warnings
from app.analytical.mmck import _stationary_distribution, mmc_metrics, mmck_metrics
from app.domain.service.distributions import ServiceDistribution
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.domain.validation.mmck import MAX_SERVERS

STATUS_OK = "ok"
STATUS_UNSTABLE = "unstable"
STATUS_INVALID = "invalid"

FAMILIES = ("mmc", "mmck", "erlangb", "mgc")
# Modelo do Laboratório -> família usada para dimensionar (o caso de um servidor é c = 1).
FAMILY_OF = {
    "mm1": "mmc", "mmc": "mmc", "mm1k": "mmck", "mmck": "mmck", "erlangb": "erlangb",
    "mg1": "mgc", "mgc": "mgc",
}
MAX_TABLE_ROWS = 100
_PATIENCE = 5          # c's seguidos sem melhorar o custo antes de parar a busca do ótimo


@dataclass(frozen=True)
class SizingSystem:
    """O sistema a dimensionar; só o número de servidores varia."""

    family: str
    lam: float
    mu: float | None = None                  # mmc, mmck, erlangb
    capacity: int | None = None              # mmck
    service: ServiceDistribution | None = None   # mgc

    @property
    def offered_load(self) -> float:
        """Tráfego oferecido a = λ·E[S], em Erlangs (o ρ = a/c das filas ilimitadas)."""
        return self.lam * (self.service.mean if self.family == "mgc" else 1 / self.mu)

    @property
    def exact(self) -> bool:
        """Se o nível de serviço é exato (só o M/G/c o aproxima por uma cauda exponencial)."""
        return self.family != "mgc"

    @property
    def max_servers(self) -> int:
        return min(MAX_SERVERS, self.capacity) if self.family == "mmck" else MAX_SERVERS

    @property
    def min_stable_servers(self) -> int:
        """Menor c com λ < c·μ nas filas ilimitadas; 1 nas demais (a perda limita o sistema)."""
        if self.family in ("mmc", "mgc"):
            return max(1, int(np.floor(self.offered_load)) + 1)
        return 1


@dataclass(frozen=True)
class Costs:
    server: float          # hₛ: custo de um servidor por unidade de tempo
    wait: float            # hₑ: custo de um cliente esperando, por unidade de tempo
    loss: float = 0.0      # h_perda: custo de um cliente perdido (bloqueado)


@dataclass(frozen=True)
class SizingRow:
    servers: int
    status: str                          # ok | unstable | invalid
    message: str | None
    rho: float | None = None
    p_wait: float | None = None
    Lq: float | None = None
    Wq: float | None = None
    p_block: float | None = None
    throughput: float | None = None
    service_level: float | None = None   # P(Wq ≤ t); None sem t ou no Erlang-B
    meets_target: bool | None = None     # atende à meta (nível de serviço ou bloqueio); None sem meta
    cost: float | None = None
    server_cost: float | None = None
    wait_cost: float | None = None
    loss_cost: float | None = None


def _metrics(system: SizingSystem, c: int) -> dict[str, float]:
    """rho, p_wait, Lq, Wq, p_block e throughput do modelo com c servidores."""
    f = system.family
    if f == "mmc":
        data = mmc_metrics(system.lam, system.mu, c).as_dict()
    elif f == "mmck":
        if c > system.capacity:
            raise QueueValidationError(
                f"c ({c}) não pode passar de K ({system.capacity}): K é a capacidade total.", "servers"
            )
        data = mmck_metrics(system.lam, system.mu, c, system.capacity).as_dict()
    elif f == "erlangb":
        data = erlangb_metrics(system.lam, system.mu, c).as_dict()
    else:
        data = {**mgc_metrics(system.lam, system.service, c).as_dict(), "p_block": 0.0}
    return {k: float(data[k]) for k in ("rho", "p_wait", "Lq", "Wq", "p_block", "throughput")}


def service_level(system: SizingSystem, c: int, t: float, metrics: dict[str, float]) -> float | None:
    """P(Wq ≤ t) para os clientes aceitos; None no Erlang-B (não há espera)."""
    f = system.family
    if f == "erlangb":
        return None
    if f == "mmc":
        tail = metrics["p_wait"] * np.exp(-(c * system.mu - system.lam) * t)
    elif f == "mmck":
        p = _stationary_distribution(system.lam, system.mu, c, system.capacity)
        k = system.capacity
        phases = np.arange(c, k) - c + 1                      # n − c + 1 términos para quem vê n ≥ c
        tails = gamma.sf(t, a=phases, scale=1.0 / (c * system.mu))
        tail = float(np.dot(p[c:k], tails)) / (1.0 - float(p[k])) if k > c else 0.0
    else:
        wq, pw = metrics["Wq"], metrics["p_wait"]
        tail = pw * np.exp(-t * pw / wq) if wq > 0 else 0.0
    return float(min(1.0, max(0.0, 1.0 - tail)))


def evaluate_row(
    system: SizingSystem,
    c: int,
    *,
    t: float | None = None,
    target: float | None = None,
    target_blocking: float | None = None,
    costs: Costs | None = None,
) -> SizingRow:
    """Linha da tabela para c servidores. Instável ou fora do domínio vira `status`, sem exceção."""
    try:
        m = _metrics(system, c)
    except UnstableSystemError as error:
        return SizingRow(c, STATUS_UNSTABLE, str(error))
    except QueueValidationError as error:
        return SizingRow(c, STATUS_INVALID, str(error))

    level = service_level(system, c, t, m) if t is not None else None
    meets = None
    if system.family == "erlangb":
        if target_blocking is not None:
            meets = m["p_block"] <= target_blocking
    elif level is not None and target is not None:
        meets = level >= target - 1e-12

    row = SizingRow(
        c, STATUS_OK, None, rho=m["rho"], p_wait=m["p_wait"], Lq=m["Lq"], Wq=m["Wq"],
        p_block=m["p_block"], throughput=m["throughput"], service_level=level, meets_target=meets,
    )
    if costs is not None:
        server = c * costs.server
        wait = m["throughput"] * m["Wq"] * costs.wait          # λ_ef · Wq · hₑ
        loss = system.lam * m["p_block"] * costs.loss          # λ · B · h_perda
        row = SizingRow(**{**row.__dict__, "cost": server + wait + loss,
                           "server_cost": server, "wait_cost": wait, "loss_cost": loss})
    return row


def table(system: SizingSystem, c_min: int, c_max: int, **options) -> list[SizingRow]:
    """Linhas de c_min a c_max (c fora de [1, máx] é recusado antes, na validação do pedido)."""
    return [evaluate_row(system, c, **options) for c in range(c_min, c_max + 1)]


def smallest_servers_for_sla(system: SizingSystem, t: float, target: float) -> SizingRow:
    """Menor c cujo P(Wq ≤ t) atinge `target`. O nível de serviço cresce com c, então para no primeiro."""
    if system.family == "erlangb":
        raise QueueValidationError("O Erlang-B não tem espera: use o bloqueio alvo.", "model")
    for c in range(system.min_stable_servers, system.max_servers + 1):
        row = evaluate_row(system, c, t=t, target=target)
        if row.status == STATUS_OK and row.meets_target:
            return row
    raise QueueValidationError(
        f"Nem {system.max_servers} servidores atingem {target:.4g} de nível de serviço em t = {t:g}.",
        "target",
    )


@dataclass(frozen=True)
class CostResult:
    best: SizingRow
    rows: list[SizingRow]
    c_min: int
    c_max: int
    at_boundary: bool      # o ótimo caiu numa ponta da faixa pedida: o verdadeiro pode estar fora


def minimize_cost(
    system: SizingSystem, costs: Costs, *, c_min: int | None = None, c_max: int | None = None,
    t: float | None = None, target: float | None = None,
) -> CostResult:
    """c que minimiza o custo total. Linhas instáveis aparecem, mas nunca são escolhidas.

    Sem faixa, parte do menor c estável e segue até o custo parar de melhorar (a curva tem um só
    vale). Com faixa, procura o mínimo dentro dela.
    """
    explicit = c_min is not None or c_max is not None
    lo = c_min if c_min is not None else system.min_stable_servers
    hi = c_max if c_max is not None else system.max_servers
    rows: list[SizingRow] = []
    best: SizingRow | None = None
    worse = 0
    for c in range(lo, hi + 1):
        row = evaluate_row(system, c, t=t, target=target, costs=costs)
        rows.append(row)
        if row.status != STATUS_OK:
            continue
        if best is None or row.cost < best.cost:
            best, worse = row, 0
        else:
            worse += 1
            if not explicit and worse >= _PATIENCE:
                break
    if best is None:
        raise QueueValidationError("Nenhum número de servidores da faixa deixa o sistema estável.", "servers")
    last = rows[-1].servers
    return CostResult(best, rows, lo, last, explicit and best.servers in (lo, last))


def approximation_warnings(system: SizingSystem, rows: list[SizingRow]) -> list[str]:
    """Avisos do M/G/c: o nível de serviço é aproximado e a aproximação tem faixa de validade."""
    if system.family != "mgc":
        return []
    notes = [
        "M/G/c: o nível de serviço usa a cauda exponencial P(Wq>t) ≈ P(esperar)·exp(−t·P(esperar)/Wq), "
        "exata só com CV = 1 (e Wq pela aproximação de Allen–Cunneen). Confira com a simulação."
    ]
    seen: set[str] = set()
    for row in rows:
        if row.status == STATUS_OK:
            for message in validity_warnings(row.rho, system.service.cv, row.servers):
                if message not in seen:
                    seen.add(message)
                    notes.append(f"c = {row.servers}: {message}")
    return notes
