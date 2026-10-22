"""Rotas do dimensionamento (Fase 11): tabela por número de servidores, nível de serviço e custo."""

import math
from dataclasses import asdict

from fastapi import APIRouter

from app.analytical.erlangb import erlangb_size, validate_target_blocking
from app.analytical.sizing import (
    FAMILY_OF,
    MAX_TABLE_ROWS,
    STATUS_OK,
    Costs,
    SizingRow,
    SizingSystem,
    approximation_warnings,
    minimize_cost,
    smallest_servers_for_sla,
    table,
)
from app.api.schemas import ErrorResponse
from app.api.schemas_sizing import (
    SizingBase,
    SizingCostRequest,
    SizingCostResponse,
    SizingSlaRequest,
    SizingSlaResponse,
    SizingTableRequest,
    SizingTableResponse,
)
from app.domain.service.distributions import build_distribution
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.mmck import validate_capacity, validate_servers
from app.domain.validation.numbers import validate_positive_finite
from app.experiments.general import _identity_values

router = APIRouter(prefix="/api/sizing", tags=["Dimensionamento"])

_errors = {422: {"model": ErrorResponse, "description": "Parâmetros inválidos"}}
_WINDOW_BELOW, _WINDOW_ABOVE = 1, 2          # padrão da tabela: c − 1 a c + 2


# ---------- validação do pedido ----------

def _unit_interval(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value) or not 0 < value < 1:
        raise QueueValidationError(f"{name} deve estar entre 0 e 1 (exclusivo).", name)
    return float(value)


def _non_negative(name: str, value: float | None) -> float | None:
    if value is None:
        return None
    if not math.isfinite(value) or value < 0:
        raise QueueValidationError(f"{name} deve ser um número finito maior ou igual a zero.", name)
    return float(value)


def _system(request: SizingBase) -> tuple[SizingSystem, int]:
    """Sistema a dimensionar e o c base do Laboratório."""
    family = FAMILY_OF[request.model]
    lam = validate_positive_finite("λ", request.lam)
    base = validate_servers(request.servers) if request.servers is not None else 1
    if family == "mgc":
        if request.service is None:
            raise QueueValidationError(f"service é obrigatório para o modelo {request.model}.", "service")
        values = _identity_values(request.service.distribution, request.service.service_values())
        return SizingSystem("mgc", lam, service=build_distribution(request.service.distribution, values)), base
    mu = validate_positive_finite("μ", request.mu)
    capacity = None
    if family == "mmck":
        if request.capacity is None:
            raise QueueValidationError(f"capacity é obrigatório para o modelo {request.model}.", "capacity")
        capacity = validate_capacity(request.capacity, 1)
        base = min(base, capacity)
    return SizingSystem(family, lam, mu=mu, capacity=capacity), base


def _costs(request: SizingBase, system: SizingSystem, *, required: bool) -> Costs | None:
    server = _non_negative("server_cost", request.server_cost)
    wait = _non_negative("wait_cost", request.wait_cost)
    loss = _non_negative("loss_cost", request.loss_cost)
    if server is None and wait is None and loss is None and not required:
        return None
    for name, value in (("server_cost", server), ("wait_cost", wait)):
        if value is None:
            raise QueueValidationError(f"{name} é obrigatório para calcular o custo.", name)
    if server <= 0:
        raise QueueValidationError(
            "server_cost deve ser maior que zero: sem custo por servidor, o ótimo seria sempre o máximo.", "server_cost"
        )
    if system.family == "erlangb" and not loss:
        raise QueueValidationError(
            "No Erlang-B o custo exige loss_cost > 0: sem custo de perda, o ótimo seria sempre c = 1.", "loss_cost"
        )
    return Costs(server, wait, loss or 0.0)


def _goal(request: SizingBase, system: SizingSystem):
    """(t, target, target_blocking) validados. O Erlang-B só tem meta de bloqueio."""
    t = _non_negative("t", request.t)
    target = _unit_interval("target", request.target)
    blocking = _unit_interval("target_blocking", request.target_blocking)
    if blocking is not None:
        blocking = validate_target_blocking(blocking)
    if (t is None) != (target is None):
        raise QueueValidationError("Informe t e target juntos (nível de serviço P(Wq ≤ t) ≥ target).", "target")
    return t, target, blocking


def _window(request: SizingTableRequest | SizingCostRequest, base: int) -> tuple[int, int]:
    c_min, c_max = request.c_min, request.c_max
    if c_min is None and c_max is None:
        return max(1, base - _WINDOW_BELOW), base + _WINDOW_ABOVE
    if c_min is None:
        c_min = max(1, c_max - _WINDOW_BELOW - _WINDOW_ABOVE)
    if c_max is None:
        c_max = c_min + _WINDOW_BELOW + _WINDOW_ABOVE
    validate_servers(c_min), validate_servers(c_max)
    if c_max < c_min:
        raise QueueValidationError("c_max deve ser maior ou igual a c_min.", "c_max")
    if c_max - c_min + 1 > MAX_TABLE_ROWS:
        raise QueueValidationError(f"A faixa tem mais de {MAX_TABLE_ROWS} linhas; reduza c_min..c_max.", "c_max")
    return c_min, c_max


def _header(request: SizingBase, system: SizingSystem, base: int, rows: list[SizingRow]) -> dict:
    return {
        "model": request.model, "family": system.family, "exact": system.exact,
        "offered_load": system.offered_load, "servers_base": base,
        "service": system.service.describe() if system.service is not None else None,
        "warnings": approximation_warnings(system, rows),
    }


def _out(row: SizingRow) -> dict:
    return asdict(row)


# ---------- rotas ----------

@router.post("/table", response_model=SizingTableResponse, responses=_errors)
def sizing_table(request: SizingTableRequest) -> SizingTableResponse:
    """Tabela por número de servidores: ρ, P(esperar), Lq, Wq, bloqueio, nível de serviço e custo.

    Linhas instáveis (ou com c > K) aparecem sinalizadas e nunca são escolhidas.
    """
    system, base = _system(request)
    t, target, blocking = _goal(request, system)
    costs = _costs(request, system, required=False)
    c_min, c_max = _window(request, base)
    rows = table(system, c_min, c_max, t=t, target=target, target_blocking=blocking, costs=costs)
    ok = [r for r in rows if r.status == STATUS_OK]
    meeting = next((r.servers for r in ok if r.meets_target), None)
    cheapest = min((r for r in ok if r.cost is not None), key=lambda r: r.cost, default=None)
    return SizingTableResponse.model_validate({
        **_header(request, system, base, rows), "rows": [_out(r) for r in rows],
        "first_meeting_target": meeting, "min_cost_servers": cheapest.servers if cheapest else None,
    })


@router.post("/sla", response_model=SizingSlaResponse, responses=_errors)
def sizing_sla(request: SizingSlaRequest) -> SizingSlaResponse:
    """Menor c que atinge a meta: P(Wq ≤ t) ≥ target (ou, no Erlang-B, B(c, a) ≤ target_blocking)."""
    system, base = _system(request)
    t, target, blocking = _goal(request, system)
    if system.family == "erlangb":
        if blocking is None:
            raise QueueValidationError("No Erlang-B a meta é o bloqueio: informe target_blocking.", "target_blocking")
        c = _first_blocking(system, blocking)
    else:
        if t is None:
            raise QueueValidationError("Informe t e target (ex.: 80% em até 20 s).", "target")
        c = smallest_servers_for_sla(system, t, target).servers
    options = {"t": t, "target": target, "target_blocking": blocking}
    rows = table(system, max(1, c - 2), min(system.max_servers, c + 1), **options)
    chosen = next(r for r in rows if r.servers == c)
    return SizingSlaResponse.model_validate({
        **_header(request, system, base, rows), "t": t, "target": target, "target_blocking": blocking,
        "servers": c, "row": _out(chosen), "rows": [_out(r) for r in rows],
    })


def _first_blocking(system: SizingSystem, target: float) -> int:
    """Menor c com B(c, a) ≤ alvo (a mesma busca do /api/models/erlangb/size)."""
    return erlangb_size(system.lam, system.mu, target).servers


@router.post("/cost", response_model=SizingCostResponse, responses=_errors)
def sizing_cost(request: SizingCostRequest) -> SizingCostResponse:
    """c que minimiza C(c) = c·hₛ + λ·(1 − B)·Wq·hₑ + λ·B·h_perda, com o gráfico custo × c."""
    system, base = _system(request)
    t, target, _ = _goal(request, system)
    costs = _costs(request, system, required=True)
    explicit = request.c_min is not None or request.c_max is not None
    c_min, c_max = _window(request, base) if explicit else (None, None)
    result = minimize_cost(system, costs, c_min=c_min, c_max=c_max, t=t, target=target)
    return SizingCostResponse.model_validate({
        **_header(request, system, base, result.rows), "optimal_servers": result.best.servers,
        "optimal_cost": result.best.cost, "row": _out(result.best), "rows": [_out(r) for r in result.rows],
        "c_min": result.c_min, "c_max": result.c_max, "at_boundary": result.at_boundary,
    })

