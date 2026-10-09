import json

import numpy as np
import pytest

from app.analytical.mm1 import mm1_metrics
from app.analytical.mmck import queue_metrics
from app.domain.validation.errors import (
    InsufficientSampleError,
    QueueValidationError,
    UnstableSystemError,
)
from app.simulation.mmck import run_replication, simulate_mmck
from app.simulation.results import QUEUE_METRIC_NAMES


def rng():
    return np.random.default_rng(0)


def det(lam, mu, c, K, T, warmup, gap, svc):
    """Replicação com chegadas e serviços determinísticos (resposta exata conhecida)."""
    return run_replication(lam, mu, c, K, T, warmup, rng(), interarrival=lambda: gap, service=lambda: svc)


# ---------- corretude do motor (casos determinísticos) ----------

def test_loss_system_blocks_two_of_every_three():
    # c=1, K=1: chegadas a cada 1,0 e serviço de 2,5 → atende 1 a cada 3 chegadas
    r = det(1, 0.4, 1, 1, 3000, 0, 1.0, 2.5)
    assert r.p_block == pytest.approx(2 / 3, abs=0.005)
    assert r.rho == pytest.approx(2.5 / 3, abs=0.005)
    assert r.throughput == pytest.approx(1 / 3, abs=0.005)
    assert r.L == pytest.approx(r.rho, abs=1e-9)        # K=1: no sistema há 0 ou 1 cliente
    assert r.Lq == 0 and r.Wq == 0 and r.p_wait == 0
    assert r.W == pytest.approx(2.5)


def test_two_servers_without_queue():
    # chegadas a cada 1,0 e serviço de 1,5 com 2 servidores: ninguém espera
    r = det(1, 1 / 1.5, 2, None, 3000, 0, 1.0, 1.5)
    assert r.rho == pytest.approx(0.75, abs=0.005)
    assert r.L == pytest.approx(1.5, abs=0.01)
    assert r.Lq == 0 and r.Wq == 0 and r.p_wait == 0 and r.p_block == 0
    assert r.W == pytest.approx(1.5)
    assert r.throughput == pytest.approx(1.0, abs=0.005)


def test_saturated_finite_system():
    # c=2, K=10, chegadas a cada 0,25 e serviço de 1,1: servidores sempre ocupados
    r = det(4, 1 / 1.1, 2, 10, 1050, 50, 0.25, 1.1)
    assert r.rho == pytest.approx(1.0, abs=0.001)
    assert r.throughput == pytest.approx(2 / 1.1, abs=0.02)         # c·μ
    assert r.p_block == pytest.approx(1 - (2 / 1.1) / 4, abs=0.01)
    assert r.p_wait == pytest.approx(1.0, abs=0.01)
    assert r.L == pytest.approx(10, abs=0.35)                        # sistema quase sempre cheio


def test_warmup_shortens_observation_window():
    r = det(1, 0.4, 1, 1, 3000, 100, 1.0, 2.5)
    assert r.observation_time == pytest.approx(2900)
    assert r.p_block == pytest.approx(2 / 3, abs=0.01)


@pytest.mark.parametrize("c,K", [(1, None), (3, None), (1, 5), (3, 6)])
def test_in_system_equals_queue_plus_in_service(c, K):
    # identidade exata: L = Lq + c·ρ (n_sistema = n_fila + n_em_atendimento)
    r = run_replication(2.0, 1.0, c, K, 500, 20, np.random.default_rng(3))
    assert r.L == pytest.approx(r.Lq + c * r.rho, rel=1e-9)


# ---------- concordância com o modelo analítico ----------

CONFIGS = {
    "M/M/2":   (1.5, 1.0, 2, None),
    "M/M/1/5": (1.2, 1.0, 1, 5),
    "M/M/3/6": (2.5, 1.0, 3, 6),
    "M/M/2/4 sobrecarregado": (3.0, 1.0, 2, 4),
}


@pytest.fixture(scope="module", params=list(CONFIGS), ids=list(CONFIGS))
def case(request):
    lam, mu, c, K = CONFIGS[request.param]
    # nível 99,99%: o valor analítico só sai do intervalo se houver viés real
    result = simulate_mmck(lam, mu, c, K, 5000, replications=10, warmup_time=500,
                           seed=11, confidence_level=0.9999)
    return result, queue_metrics(lam, mu, c, K).as_dict()


@pytest.mark.parametrize("metric", QUEUE_METRIC_NAMES)
def test_analytical_value_inside_wide_interval(case, metric):
    result, exact = case
    s = result.summary[metric]
    assert s.ci_low <= exact[metric] <= s.ci_high


# métricas de baixa variância também precisam ficar próximas (tolerâncias ~2x o pior erro observado)
@pytest.mark.parametrize("metric,tol", [("rho", 0.03), ("throughput", 0.03), ("p_wait", 0.06)])
def test_low_variance_metrics_are_close(case, metric, tol):
    result, exact = case
    assert result.summary[metric].mean == pytest.approx(exact[metric], rel=tol)


def test_blocking_probability_is_close(case):
    result, exact = case
    if exact["p_block"] == 0:
        assert result.summary["p_block"].mean == 0
    else:
        assert result.summary["p_block"].mean == pytest.approx(exact["p_block"], rel=0.08)


def test_littles_law_holds_in_simulation(case):
    result, _ = case
    s = result.summary
    assert s["L"].mean == pytest.approx(s["throughput"].mean * s["W"].mean, rel=0.06)


def test_one_server_infinite_capacity_matches_mm1():
    # o modelo geral com c=1 e K=∞ reproduz o M/M/1 analítico já validado
    result = simulate_mmck(1, 2, 1, None, 5000, replications=10, warmup_time=200,
                           seed=5, confidence_level=0.9999)
    exact = mm1_metrics(1, 2)
    for name in ("rho", "L", "Lq", "W", "Wq"):
        s = result.summary[name]
        assert s.ci_low <= getattr(exact, name) <= s.ci_high
    assert result.summary["p_wait"].mean == pytest.approx(0.5, rel=0.06)   # P(esperar) = ρ


def test_infinite_capacity_never_blocks():
    result = simulate_mmck(1.5, 1, 2, None, 300, replications=3, seed=1)
    assert all(run.p_block == 0 for run in result.runs)


# ---------- estrutura, reprodutibilidade e serialização ----------

def test_summary_structure():
    r = simulate_mmck(2.5, 1, 3, 6, 300, replications=4, seed=1)
    assert set(r.summary) == set(QUEUE_METRIC_NAMES)
    assert (r.servers, r.capacity, r.replications, len(r.runs)) == (3, 6, 4, 4)
    for s in r.summary.values():
        assert s.n == 4
        assert s.ci_low <= s.mean <= s.ci_high


def test_same_seed_gives_same_result():
    a = simulate_mmck(2.5, 1, 3, 6, 300, replications=3, seed=7)
    b = simulate_mmck(2.5, 1, 3, 6, 300, replications=3, seed=7)
    assert a.runs == b.runs


def test_different_seed_or_replication_gives_different_result():
    a = simulate_mmck(2.5, 1, 3, 6, 300, replications=3, seed=7)
    b = simulate_mmck(2.5, 1, 3, 6, 300, replications=3, seed=8)
    assert a.runs != b.runs
    assert len({run.L for run in a.runs}) == 3


def test_random_seed_is_reported_in_json_safe_range_and_reproducible():
    a = simulate_mmck(2.5, 1, 3, 6, 200, replications=2)
    assert 0 <= a.seed < 2**53
    b = simulate_mmck(2.5, 1, 3, 6, 200, replications=2, seed=a.seed)
    assert a.runs == b.runs


def test_a_single_replication_is_rejected_and_two_always_give_an_interval():
    with pytest.raises(QueueValidationError) as exc:
        simulate_mmck(2.5, 1, 3, 6, 300, replications=1, seed=1)
    assert exc.value.field == "replications"
    s = simulate_mmck(2.5, 1, 3, 6, 300, replications=2, seed=1).summary["L"]
    assert s.n == 2 and s.std is not None and s.ci_low is not None


def test_result_is_json_serializable():
    json.dumps(simulate_mmck(2.5, 1, 3, 6, 200, replications=2, seed=1).as_dict())
    json.dumps(simulate_mmck(1.5, 1, 2, None, 200, replications=2, seed=1).as_dict())   # capacity None


# ---------- validação ----------

def test_infinite_capacity_requires_stability():
    with pytest.raises(UnstableSystemError):
        simulate_mmck(2, 1, 2, None, 100)             # λ = c·μ
    with pytest.raises(UnstableSystemError):
        simulate_mmck(3, 1, 2, None, 100)


def test_finite_capacity_accepts_overload():
    r = simulate_mmck(10, 1, 2, 5, 100, replications=2, seed=1)
    assert r.summary["p_block"].mean > 0.5


@pytest.mark.parametrize(
    "kwargs",
    [
        {"servers": 0}, {"servers": 1.5}, {"servers": True},
        {"capacity": 1},                  # K < c (com servers=2)
        {"capacity": 0}, {"capacity": 2.5},
        {"simulation_time": 0}, {"replications": 0}, {"replications": 1}, {"replications": 101}, {"warmup_time": 100},
        {"seed": -1}, {"seed": 2**53}, {"confidence_level": 1.5},
    ],
)
def test_invalid_settings(kwargs):
    params = {"lam": 1, "mu": 1, "servers": 2, "capacity": 5, "simulation_time": 100, **kwargs}
    with pytest.raises(QueueValidationError):
        simulate_mmck(**params)


def test_oversized_simulation_is_rejected():
    with pytest.raises(QueueValidationError, match="grande demais"):
        simulate_mmck(40, 50, 2, 10, 1_000_000, replications=10)


def test_too_short_simulation_raises_insufficient_sample():
    with pytest.raises(InsufficientSampleError):
        simulate_mmck(1, 2, 2, 5, 0.001, replications=2, seed=1)
