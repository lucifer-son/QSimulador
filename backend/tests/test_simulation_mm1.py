import json

import numpy as np
import pytest

from app.analytical.mm1 import mm1_metrics
from app.domain.validation.errors import (
    InsufficientSampleError,
    QueueValidationError,
    UnstableSystemError,
)
from app.simulation.mm1 import run_replication, simulate_mm1

# Tolerâncias relativas calibradas pela variação entre sementes
# (λ=1, μ=2, T=5000, warm-up=200, 10 réplicas): ~2x o pior erro observado.
TOLERANCE = {"rho": 0.03, "L": 0.06, "Lq": 0.10, "W": 0.06, "Wq": 0.10}


def rng():
    return np.random.default_rng(0)


# ---------- corretude do motor (casos determinísticos, resposta exata) ----------

def test_dd1_known_values():
    # Chegadas a cada 1,0 e serviço de 0,5: nunca há fila.
    r = run_replication(1, 2, 1000, 0, rng(), interarrival=lambda: 1.0, service=lambda: 0.5)
    assert r.rho == pytest.approx(0.5, abs=0.01)
    assert r.L == pytest.approx(0.5, abs=0.01)
    assert r.Lq == pytest.approx(0.0, abs=1e-9)
    assert r.W == pytest.approx(0.5)
    assert r.Wq == pytest.approx(0.0, abs=1e-9)
    assert r.throughput == pytest.approx(1.0, abs=0.01)


def test_queue_builds_when_arrivals_outpace_service():
    # Chegadas a cada 0,5 e serviço de 1,0 (instável de propósito):
    # o nº no sistema cresce ~linearmente, então L ≈ T/2 e Lq ≈ L - 1.
    r = run_replication(2, 1, 100, 0, rng(), interarrival=lambda: 0.5, service=lambda: 1.0)
    assert r.rho == pytest.approx(1.0, abs=0.02)
    assert r.L == pytest.approx(50, rel=0.05)
    assert r.Lq == pytest.approx(r.L - 1, abs=0.1)
    assert r.Wq > 0


def test_warmup_shortens_observation_window():
    r = run_replication(1, 2, 1000, 100, rng(), interarrival=lambda: 1.0, service=lambda: 0.5)
    assert r.observation_time == pytest.approx(900)
    assert r.rho == pytest.approx(0.5, abs=0.01)
    assert r.L == pytest.approx(0.5, abs=0.01)


# ---------- concordância com o modelo analítico ----------

@pytest.fixture(scope="module")
def result():
    return simulate_mm1(1, 2, 5000, replications=10, warmup_time=200, seed=42)


@pytest.mark.parametrize("metric", ["rho", "L", "Lq", "W", "Wq"])
def test_simulation_matches_analytical(result, metric):
    expected = getattr(mm1_metrics(1, 2), metric)
    simulated = result.summary[metric].mean
    assert simulated == pytest.approx(expected, rel=TOLERANCE[metric])


def test_throughput_matches_arrival_rate(result):
    # Em regime estável, a vazão de saída é igual à taxa de chegada.
    assert result.summary["throughput"].mean == pytest.approx(1.0, rel=0.03)


def test_littles_law_holds_in_simulation(result):
    s = result.summary
    assert s["L"].mean == pytest.approx(s["throughput"].mean * s["W"].mean, rel=0.06)


def test_summary_structure(result):
    assert result.replications == 10
    assert len(result.runs) == 10
    for name, s in result.summary.items():
        assert s.n == 10
        assert s.ci_low <= s.mean <= s.ci_high
        assert s.std > 0


# ---------- reprodutibilidade ----------

def test_same_seed_gives_same_result():
    a = simulate_mm1(1, 2, 300, replications=3, seed=7)
    b = simulate_mm1(1, 2, 300, replications=3, seed=7)
    assert a.runs == b.runs


def test_different_seed_gives_different_result():
    a = simulate_mm1(1, 2, 300, replications=3, seed=7)
    b = simulate_mm1(1, 2, 300, replications=3, seed=8)
    assert a.runs != b.runs


def test_replications_are_independent():
    r = simulate_mm1(1, 2, 300, replications=3, seed=7)
    assert len({run.L for run in r.runs}) == 3


def test_random_seed_is_reported_and_reproducible():
    a = simulate_mm1(1, 2, 300, replications=2)
    assert isinstance(a.seed, int)
    b = simulate_mm1(1, 2, 300, replications=2, seed=a.seed)
    assert a.runs == b.runs


# ---------- uma única replicação / serialização ----------

def test_single_replication_has_no_interval():
    r = simulate_mm1(1, 2, 300, replications=1, seed=1)
    s = r.summary["L"]
    assert s.n == 1
    assert s.std is None and s.ci_low is None and s.ci_high is None


def test_result_is_json_serializable():
    r = simulate_mm1(1, 2, 300, replications=2, seed=1)
    json.dumps(r.as_dict())


# ---------- validação de parâmetros ----------

def test_unstable_system_is_rejected():
    with pytest.raises(UnstableSystemError):
        simulate_mm1(50, 50, 100)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"simulation_time": 0},
        {"simulation_time": -10},
        {"simulation_time": float("inf")},
        {"replications": 0},
        {"replications": 2.5},
        {"replications": True},
        {"warmup_time": -1},
        {"warmup_time": 100},        # igual a simulation_time
        {"warmup_time": 150},        # maior que simulation_time
        {"seed": -1},
        {"seed": 1.5},
        {"seed": 2**53},          # acima do limite seguro para JSON
        {"confidence_level": 0},
        {"confidence_level": 1},
        {"confidence_level": 1.5},
    ],
)
def test_invalid_settings(kwargs):
    params = {"lam": 1, "mu": 2, "simulation_time": 100, **kwargs}
    with pytest.raises(QueueValidationError):
        simulate_mm1(**params)


def test_oversized_simulation_is_rejected():
    with pytest.raises(QueueValidationError, match="grande demais"):
        simulate_mm1(40, 50, 1_000_000, replications=10)


def test_random_seed_fits_in_json_safe_range():
    # Inteiros acima de 2^53 perdem precisão em JavaScript.
    assert 0 <= simulate_mm1(1, 2, 100, replications=1).seed < 2**53


def test_max_seed_is_accepted():
    simulate_mm1(1, 2, 50, replications=1, seed=2**53 - 1)


def test_too_short_simulation_raises_insufficient_sample():
    # Tempo tão curto que, na prática, nenhum cliente chega.
    with pytest.raises(InsufficientSampleError):
        simulate_mm1(1, 2, 0.001, replications=2, seed=1)
