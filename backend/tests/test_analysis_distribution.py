"""P(n) e P(Wq > t) analíticas (Fase 13, RFC-22 e RFC-23)."""

import math

import numpy as np
import pytest

from app.analysis.distribution import (
    MAX_STATES, state_distribution, wait_percentile_mmc, wait_survival_mmc, wait_tail_mmc,
)
from app.analytical.mm1 import mm1_metrics
from app.analytical.mmck import mmc_metrics, mmck_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError

CASES = [
    ("mm1", 8, 10, 1, None), ("mmc", 15, 10, 2, None), ("mmc", 45, 10, 5, None),
    ("mm1k", 15, 10, 1, 5), ("mmck", 15, 10, 2, 6), ("mmck", 25, 10, 3, 40),
]


@pytest.mark.parametrize("model,lam,mu,c,k", CASES)
def test_p_of_n_sums_to_one_and_matches_the_mean(model, lam, mu, c, k):
    d = state_distribution(model, lam, mu, c, k)
    assert sum(d.p) + d.omitted_mass == pytest.approx(1.0, abs=1e-12)
    assert d.cumulative[-1] == pytest.approx(sum(d.p))
    assert all(x >= 0 for x in d.p)
    if model in ("mm1", "mmc"):
        assert sum(n * p for n, p in zip(d.states, d.p)) == pytest.approx(d.mean, rel=1e-4)   # cauda < 1e-6
    else:
        assert sum(n * p for n, p in zip(d.states, d.p)) == pytest.approx(d.mean, rel=1e-12)


def test_mm1_is_geometric_with_p0_equal_to_one_minus_rho():
    d = state_distribution("mm1", 8, 10)
    rho = 0.8
    assert d.p0 == pytest.approx(1 - rho)
    assert d.p[0] == pytest.approx(1 - rho)
    assert d.p[:5] == pytest.approx([(1 - rho) * rho**n for n in range(5)])
    assert d.mean == pytest.approx(mm1_metrics(8, 10).L)
    assert d.omitted_mass == pytest.approx(rho ** len(d.states))      # cauda geométrica exata


def test_mmc_tail_is_exact_and_p_wait_is_erlang_c():
    d = state_distribution("mmc", 15, 10, 2)
    m = mmc_metrics(15, 10, 2)
    assert d.p_wait == pytest.approx(m.p_wait)
    assert sum(d.p[2:]) + d.omitted_mass == pytest.approx(m.p_wait)   # P(N ≥ c) = Erlang C
    assert d.p0 == pytest.approx(m.p0)


def test_finite_capacity_matches_the_known_metrics():
    d = state_distribution("mmck", 15, 10, 2, 6)
    m = mmck_metrics(15, 10, 2, 6)
    assert d.states == list(range(7))
    assert d.p[-1] == pytest.approx(m.p_block)
    assert d.p_block == pytest.approx(m.p_block)
    assert d.mean == pytest.approx(m.L)


def test_deterministic_two_state_case():
    # M/M/1/1 (perda pura, um servidor): P(0) = μ/(λ+μ), P(1) = λ/(λ+μ).
    d = state_distribution("mm1k", 3, 1, 1, 1)
    assert d.p == pytest.approx([0.25, 0.75])


def test_huge_capacity_returns_a_window_with_the_omitted_mass():
    d = state_distribution("mm1k", 15, 10, 1, 5000)      # ρ = 1,5: a massa fica perto de K
    assert len(d.states) <= MAX_STATES
    assert d.states[-1] == 5000
    assert d.omitted_mass < 1e-5
    assert sum(d.p) + d.omitted_mass == pytest.approx(1.0)


def test_heavy_traffic_is_capped_and_reports_the_tail():
    d = state_distribution("mm1", 9.99, 10)
    assert len(d.states) == MAX_STATES
    assert d.omitted_mass > 0.5


def test_general_service_and_erlangb_have_no_p_of_n():
    for model in ("mg1", "mgc", "erlangb"):
        with pytest.raises(QueueValidationError) as e:
            state_distribution(model, 5, 10, 2)
        assert e.value.field == "model"


def test_unstable_and_missing_capacity_are_rejected():
    with pytest.raises(UnstableSystemError):
        state_distribution("mm1", 12, 10)
    with pytest.raises(QueueValidationError) as e:
        state_distribution("mmck", 5, 10, 2, None)
    assert e.value.field == "capacity"


# ---------- P(Wq > t) ----------

def test_mm1_wait_tail_closed_form():
    t = wait_tail_mmc("mm1", 8, 10, points=30)
    ts = np.array(t.t)
    assert t.t[0] == 0.0
    assert t.survival[0] == pytest.approx(0.8)                     # P(Wq > 0) = ρ
    assert t.survival == pytest.approx(list(0.8 * np.exp(-2 * ts)))
    assert t.mean_wait == pytest.approx(mm1_metrics(8, 10).Wq)
    assert t.survival[-1] == pytest.approx(1e-4, rel=1e-6)


def test_mmc_wait_tail_integrates_to_the_mean_wait():
    t = wait_tail_mmc("mmc", 15, 10, 2)
    m = mmc_metrics(15, 10, 2)
    assert t.p_wait == pytest.approx(m.p_wait)
    assert t.mean_wait == pytest.approx(m.Wq)
    # Wq = ∫ P(Wq > t) dt (trapézios até a cauda de 1e-4: erro ≤ ~1e-5)
    area = np.trapezoid(t.survival, t.t)
    assert area == pytest.approx(m.Wq, rel=2e-3)


def test_percentiles_invert_the_tail():
    t = wait_tail_mmc("mmc", 15, 10, 2)
    p90 = t.percentiles["p90"]
    assert wait_survival_mmc(15, 10, 2, p90) == pytest.approx(0.10)
    # p50: 35,7 % dos clientes não esperam, então a mediana ainda é positiva só se P(esperar) > 50 %
    assert t.percentiles["p50"] == pytest.approx(wait_percentile_mmc(t.p_wait, t.decay_rate, 0.5))
    # Sistema quase vazio: ninguém espera até o percentil 90.
    low = wait_tail_mmc("mmc", 2, 10, 3)
    assert low.percentiles["p90"] == 0.0


def test_wait_tail_rejects_other_models_and_unstable_points():
    with pytest.raises(QueueValidationError):
        wait_tail_mmc("mmck", 5, 10, 2)
    with pytest.raises(UnstableSystemError):
        wait_tail_mmc("mmc", 25, 10, 2)
    with pytest.raises(QueueValidationError):
        wait_tail_mmc("mm1", 5, 10, points=1)
    with pytest.raises(QueueValidationError):
        wait_tail_mmc("mm1", 5, 10, t_max=-1)


def test_scalar_survival_helper():
    assert wait_survival_mmc(8, 10, 1, 0.0) == pytest.approx(0.8)
    assert wait_survival_mmc(8, 10, 1, 0.5) == pytest.approx(0.8 * math.exp(-1.0))
