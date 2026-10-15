"""Simulação do M/M/c//N, conferida com o analítico de população finita."""

import numpy as np
import pytest

from app.analytical.finite_population import finite_population_metrics
from app.domain.validation.errors import InsufficientSampleError, QueueValidationError
from app.simulation.finite_population import (
    max_event_rate, run_finite_population_replication, simulate_finite_population,
)
from app.simulation.results import QUEUE_METRIC_NAMES


def test_um_usuario_nunca_espera():
    r = run_finite_population_replication(1, 1.0, 4.0, 1, 2000, 100, np.random.default_rng(3))
    assert r.Lq == 0.0 and r.Wq == 0.0 and r.p_wait == 0.0
    assert r.L <= 1.0 and r.p_block == 0.0


def test_reprodutivel_e_sementes_diferentes_diferem():
    a = simulate_finite_population(5, 1.0, 3.0, 1, 300, 3, 20, seed=7)
    b = simulate_finite_population(5, 1.0, 3.0, 1, 300, 3, 20, seed=7)
    c = simulate_finite_population(5, 1.0, 3.0, 1, 300, 3, 20, seed=8)
    assert a.as_dict() == b.as_dict()
    assert a.summary["W"].mean != c.summary["W"].mean
    assert set(a.summary) == set(QUEUE_METRIC_NAMES)


@pytest.mark.parametrize("n,z,mu,c", [(10, 1.0, 5.0, 1), (30, 2.0, 2.0, 3), (6, 0.5, 4.0, 2)])
def test_concorda_com_o_analitico(n, z, mu, c):
    exact = finite_population_metrics(mu, c, n, z)
    sim = simulate_finite_population(n, z, mu, c, 4000, 10, 200, seed=2026)
    for name in ("rho", "L", "W", "throughput", "p_wait"):
        assert abs(sim.summary[name].mean - getattr(exact, name)) / getattr(exact, name) < 0.03, name
    assert sim.summary["p_block"].mean == 0.0


def test_think_time_zero_e_aceito():
    r = simulate_finite_population(4, 0.0, 5.0, 1, 500, 3, 20, seed=1)
    assert r.summary["throughput"].mean == pytest.approx(5.0, rel=0.05)     # saturado: X → c·μ


def test_limite_de_eventos_usa_a_vazao_maxima():
    assert max_event_rate(10, 1.0, 5.0, 3) == pytest.approx(10 / 1.2)       # N/(Z + 1/μ), com servidores sobrando
    assert max_event_rate(10, 1.0, 5.0, 1) == pytest.approx(5.0)            # c·μ limita antes
    assert max_event_rate(1000, 0.0, 5.0, 2) == pytest.approx(10.0)         # c·μ


def test_obedece_validacao_e_limites_de_custo():
    for args, field in [((0, 1.0, 1.0, 1), "population"), ((5, -1.0, 1.0, 1), "think_time"),
                        ((5, 1.0, 0.0, 1), "mu"), ((5, 1.0, 1.0, 0), "servers")]:
        with pytest.raises(QueueValidationError) as exc:
            simulate_finite_population(*args, 100, 3, 0)
        assert exc.value.field == field
    with pytest.raises(QueueValidationError) as exc:
        simulate_finite_population(100, 0.01, 1000.0, 1, 10_000, 100, 0)
    assert exc.value.field == "simulation_time"
    with pytest.raises(QueueValidationError) as exc:
        simulate_finite_population(5, 1.0, 1.0, 1, 100, 1, 0)
    assert exc.value.field == "replications"


def test_amostra_insuficiente():
    with pytest.raises(InsufficientSampleError):
        simulate_finite_population(1, 1000.0, 1.0, 1, 1.0, 2, 0.0, seed=1)
