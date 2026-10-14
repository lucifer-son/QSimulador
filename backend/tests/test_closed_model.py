"""Modelo fechado M/M/c//N: analítico (contra a cadeia de Markov resolvida diretamente) e simulação."""

from fractions import Fraction
from math import factorial

import numpy as np
import pytest

from app.analytical.closed import closed_metrics
from app.domain.validation.errors import InsufficientSampleError, QueueValidationError
from app.simulation.closed import run_closed_replication, simulate_closed
from app.simulation.results import METRIC_NAMES


def solve_chain(n, z, mu, c):
    """Distribuição estacionária pela resolução direta de πQ = 0 (independente da fórmula)."""
    q = np.zeros((n + 1, n + 1))
    for s in range(n + 1):
        if s < n:
            q[s, s + 1] = (n - s) / z
        if s > 0:
            q[s, s - 1] = min(s, c) * mu
        q[s, s] = -q[s].sum()
    a = np.vstack([q.T, np.ones(n + 1)])
    b = np.zeros(n + 2)
    b[-1] = 1
    return np.linalg.lstsq(a, b, rcond=None)[0]


# ---------- analítico ----------

def test_um_usuario_tem_resposta_fechada():
    m = closed_metrics(1, 1.0, 4.0, 1)
    assert m.W == pytest.approx(0.25, abs=1e-12)           # sem fila: só o serviço
    assert m.Wq == pytest.approx(0.0, abs=1e-12)
    assert m.throughput == pytest.approx(1 / (1.0 + 0.25), abs=1e-12)
    assert m.rho == pytest.approx(m.throughput / 4.0, abs=1e-12)


def test_p0_do_mm1n_pela_formula_exata():
    # P0 = [Σ_{n=0..N} N!/(N-n)! · (λ/μ)^n]^-1, com λ = 1/Z (aritmética exata)
    n, z, mu = 6, Fraction(2), Fraction(3)
    a = (1 / z) / mu
    exact = 1 / sum(Fraction(factorial(n), factorial(n - k)) * a**k for k in range(n + 1))
    assert closed_metrics(n, 2.0, 3.0, 1).p0 == pytest.approx(float(exact), rel=1e-12)


@pytest.mark.parametrize("n,z,mu,c", [(5, 1.0, 2.0, 1), (12, 0.5, 1.0, 3), (30, 2.0, 0.7, 4), (8, 3.0, 5.0, 10)])
def test_confere_com_a_cadeia_de_markov(n, z, mu, c):
    p = solve_chain(n, z, mu, c)
    s = np.arange(n + 1)
    m = closed_metrics(n, z, mu, c)
    assert m.L == pytest.approx(float(s @ p), rel=1e-9)
    assert m.Lq == pytest.approx(float(np.maximum(s - c, 0) @ p), rel=1e-9, abs=1e-12)
    assert m.throughput == pytest.approx(float((n - s) @ p / z), rel=1e-9)
    assert m.p0 == pytest.approx(float(p[0]), rel=1e-9)
    assert m.rho == pytest.approx(float(np.minimum(s, c) @ p / c), rel=1e-9)


@pytest.mark.parametrize("n,z,mu,c", [(10, 1.0, 5.0, 1), (40, 0.3, 2.0, 3), (7, 5.0, 1.0, 2)])
def test_leis_de_little_e_da_resposta_interativa(n, z, mu, c):
    m = closed_metrics(n, z, mu, c)
    assert m.L == pytest.approx(m.throughput * m.W, rel=1e-12)
    assert m.Lq == pytest.approx(m.throughput * m.Wq, rel=1e-12)
    assert n == pytest.approx(m.throughput * (m.W + z), rel=1e-12)      # N = X·(W + Z)
    assert m.W == pytest.approx(m.Wq + 1 / mu, rel=1e-9)
    assert m.rho == pytest.approx(m.throughput / (c * mu), rel=1e-9)


def test_sem_fila_quando_servidores_sobram():
    m = closed_metrics(5, 1.0, 2.0, 5)                       # c >= N: ninguém espera
    assert m.Lq == pytest.approx(0.0, abs=1e-12)
    assert m.W == pytest.approx(0.5, rel=1e-12)


def test_saturacao_aproxima_a_capacidade_e_n_grande_e_estavel():
    m = closed_metrics(2000, 0.01, 10.0, 2)                  # muita carga: X → c·μ = 20
    assert m.throughput == pytest.approx(20.0, rel=1e-3)
    assert m.rho == pytest.approx(1.0, rel=1e-3)
    big = closed_metrics(100_000, 1.0, 50.0, 3)
    assert np.isfinite([big.L, big.W, big.throughput]).all()


def test_vazao_cresce_e_resposta_cresce_com_n():
    xs = [closed_metrics(n, 1.0, 5.0, 1) for n in (1, 5, 10, 20)]
    assert all(a.throughput < b.throughput for a, b in zip(xs, xs[1:]))
    assert all(a.W < b.W for a, b in zip(xs, xs[1:]))


@pytest.mark.parametrize("args,field", [
    ((0, 1.0, 1.0, 1), "users"), ((1.5, 1.0, 1.0, 1), "users"), ((100_001, 1.0, 1.0, 1), "users"),
    ((5, 0.0, 1.0, 1), "think_time"), ((5, 1.0, -1.0, 1), "mu"), ((5, 1.0, 1.0, 0), "servers"),
    ((True, 1.0, 1.0, 1), "users"),
])
def test_validacao(args, field):
    with pytest.raises(QueueValidationError) as exc:
        closed_metrics(*args)
    assert exc.value.field == field


# ---------- simulação ----------

def test_um_usuario_nunca_espera_na_simulacao():
    r = run_closed_replication(1, 1.0, 4.0, 1, 2000, 100, np.random.default_rng(3))
    assert r.Lq == 0.0 and r.Wq == 0.0
    assert r.L <= 1.0


def test_reprodutivel_e_sementes_diferentes_diferem():
    a = simulate_closed(5, 1.0, 3.0, 1, 300, 3, 20, seed=7)
    b = simulate_closed(5, 1.0, 3.0, 1, 300, 3, 20, seed=7)
    c = simulate_closed(5, 1.0, 3.0, 1, 300, 3, 20, seed=8)
    assert a.as_dict() == b.as_dict()
    assert a.summary["W"].mean != c.summary["W"].mean
    assert set(a.summary) == set(METRIC_NAMES)


@pytest.mark.parametrize("n,z,mu,c", [(10, 1.0, 5.0, 1), (30, 2.0, 2.0, 3)])
def test_simulacao_concorda_com_o_analitico(n, z, mu, c):
    exact = closed_metrics(n, z, mu, c)
    sim = simulate_closed(n, z, mu, c, 4000, 10, 200, seed=2026)
    for name in ("rho", "L", "W", "throughput"):
        s = sim.summary[name]
        assert abs(s.mean - getattr(exact, name)) / getattr(exact, name) < 0.03, name


def test_simulacao_obedece_os_limites_de_custo():
    with pytest.raises(QueueValidationError) as exc:
        simulate_closed(100, 0.01, 1000.0, 1, 10_000, 100, 0)
    assert exc.value.field == "simulation_time"
    with pytest.raises(QueueValidationError) as exc:
        simulate_closed(5, 1.0, 1.0, 1, 100, 1, 0)
    assert exc.value.field == "replications"


def test_amostra_insuficiente():
    with pytest.raises(InsufficientSampleError):
        simulate_closed(1, 1000.0, 1.0, 1, 1.0, 2, 0.0, seed=1)
