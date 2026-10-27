"""P(Wq > t) por simulação FIFO (Fase 13, RFC-23): validada contra fórmulas fechadas."""

import numpy as np
import pytest

from app.analysis.distribution import wait_survival_mmc
from app.analysis.wait_simulation import fifo_waits, simulate_wait_survival, survival_at
from app.analytical.mg1 import mg1_metrics
from app.analytical.mgc import mgc_metrics
from app.analytical.mmck import mmc_metrics, mmck_metrics
from app.domain.service.distributions import build_distribution
from app.domain.validation.errors import QueueValidationError, UnstableSystemError


def inside(summary, value, slack=0.0):
    return summary.ci_low - slack <= value <= summary.ci_high + slack


# ---------- casos determinísticos (resposta exata) ----------

def test_fifo_waits_with_fixed_arrivals_and_services():
    # Chegadas em 1, 2, 3 (via amostrador fixo não é possível: usa-se o recursão direta).
    # Um servidor, serviço 1,5: esperas 0; 0,5; 1,0 (Lindley).
    class Fixed:
        def exponential(self, scale, size):
            return np.ones(size)            # chegadas a cada 1,0
    waits, offered, blocked = fifo_waits(1.0, 1, None, lambda rng, n: np.full(n, 1.5), 3.5, 0.0, Fixed())
    assert waits.tolist() == [0.0, 0.5, 1.0]
    assert (offered, blocked) == (3, 0)


def test_capacity_equal_to_servers_never_waits_and_blocks_like_erlang_b():
    r = simulate_wait_survival("mmck", 15, mu=10, servers=2, capacity=2, seed=3, replications=10)
    assert all(s.mean == 0 for s in r.survival)
    assert r.p_wait.mean == 0
    from app.analytical.erlangb import erlangb_metrics
    assert inside(r.p_block, erlangb_metrics(15, 10, 2).p_block)


def test_survival_helper_is_strict_and_empirical():
    w = np.array([0.0, 0.0, 1.0, 2.0])
    assert survival_at(w, np.array([0.0, 1.0, 2.0])).tolist() == [0.5, 0.25, 0.0]


# ---------- contra a fórmula fechada do M/M/c ----------

@pytest.mark.parametrize("model,lam,mu,c", [("mm1", 8, 10, 1), ("mmc", 15, 10, 2), ("mmc", 45, 10, 5)])
def test_simulated_tail_matches_the_closed_form(model, lam, mu, c):
    r = simulate_wait_survival(model, lam, mu=mu, servers=c, seed=11, replications=10,
                               simulation_time=50_000 / lam)
    t = np.array(r.t)
    ref = wait_survival_mmc(lam, mu, c, t)
    mean = np.array([s.mean for s in r.survival])
    covered = np.mean([inside(s, v, 1e-12) for s, v in zip(r.survival, ref)])
    assert covered >= 0.9                                      # medido: 100 % em três sementes
    assert np.abs(mean - ref).max() < 0.03                     # medido em 20 sementes: máx 0,0173 (M/M/5, ρ = 0,9)
    m = mmc_metrics(lam, mu, c)
    assert inside(r.p_wait, m.p_wait) and inside(r.mean_wait, m.Wq)


# ---------- demais modelos contra o analítico que existir ----------

def test_finite_capacity_matches_the_analytical_mean_and_blocking():
    r = simulate_wait_survival("mmck", 25, mu=10, servers=3, capacity=8, seed=5, replications=10,
                               simulation_time=2_000)
    m = mmck_metrics(25, 10, 3, 8)
    assert inside(r.p_block, m.p_block)
    assert inside(r.mean_wait, m.Wq)
    assert inside(r.p_wait, m.p_wait)


def test_mg1_matches_pollaczek_khinchine():
    service = build_distribution("lognormal", {"mean": 0.08, "cv": 1.5})
    r = simulate_wait_survival("mg1", 8, service=service, seed=2, replications=10, simulation_time=5_000)
    assert inside(r.mean_wait, mg1_metrics(8, service).Wq)


def test_mgc_with_exponential_service_is_the_mmc_tail():
    service = build_distribution("exponential", {"mean": 0.1})
    r = simulate_wait_survival("mgc", 15, service=service, servers=2, seed=4, replications=10,
                               simulation_time=3_000)
    ref = wait_survival_mmc(15, 10, 2, np.array(r.t))
    assert np.mean([inside(s, v, 1e-12) for s, v in zip(r.survival, ref)]) >= 0.9
    assert inside(r.mean_wait, mgc_metrics(15, service, 2).Wq)


def test_deterministic_service_waits_less_than_exponential():
    det = simulate_wait_survival("mg1", 8, service=build_distribution("deterministic", {"mean": 0.1}),
                                 seed=6, replications=10, simulation_time=3_000)
    assert det.mean_wait.mean == pytest.approx(0.2, rel=0.05)     # M/D/1: Wq = ρ/(2μ(1−ρ)) = 0,2


# ---------- reprodutibilidade e validação ----------

def test_same_seed_same_curve_and_seed_is_reported():
    a = simulate_wait_survival("mmc", 15, mu=10, servers=2, seed=9, replications=3, simulation_time=500)
    b = simulate_wait_survival("mmc", 15, mu=10, servers=2, seed=9, replications=3, simulation_time=500)
    assert a.as_dict() == b.as_dict() and a.seed == 9
    assert simulate_wait_survival("mmc", 15, mu=10, servers=2, replications=2, simulation_time=100).seed >= 0


def test_defaults_scale_with_lambda():
    r = simulate_wait_survival("mm1", 8, mu=10, seed=1, replications=3)
    assert r.simulation_time == pytest.approx(20_000 / 8)
    assert r.warmup_time == pytest.approx(0.1 * r.simulation_time)
    assert len(r.t) == 60 and r.t[0] == 0.0


def test_validation_errors():
    with pytest.raises(UnstableSystemError):
        simulate_wait_survival("mm1", 12, mu=10)
    with pytest.raises(QueueValidationError) as e:
        simulate_wait_survival("erlangb", 5, mu=10, servers=2)
    assert e.value.field == "model"
    with pytest.raises(QueueValidationError) as e:
        simulate_wait_survival("mg1", 5)
    assert e.value.field == "service"
    with pytest.raises(QueueValidationError) as e:
        simulate_wait_survival("mm1k", 5, mu=10)
    assert e.value.field == "capacity"
    with pytest.raises(QueueValidationError) as e:
        simulate_wait_survival("mm1", 8, mu=10, replications=1)
    assert e.value.field == "replications"
