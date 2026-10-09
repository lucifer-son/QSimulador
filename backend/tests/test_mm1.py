import math

import pytest

from app.analytical.mm1 import mm1_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError


def test_mm1_metrics():
    # Caso do README: λ = 40 req/s, μ = 50 req/s
    m = mm1_metrics(40, 50)
    assert m.rho == pytest.approx(0.8)
    assert m.L == pytest.approx(4.0)
    assert m.Lq == pytest.approx(3.2)
    assert m.W == pytest.approx(0.1)
    assert m.Wq == pytest.approx(0.08)


def test_mm1_metrics_second_known_case():
    # λ = 1, μ = 2 → ρ = 0,5; L = 1; Lq = 0,5; W = 1; Wq = 0,5
    m = mm1_metrics(1, 2)
    assert m.rho == pytest.approx(0.5)
    assert m.L == pytest.approx(1.0)
    assert m.Lq == pytest.approx(0.5)
    assert m.W == pytest.approx(1.0)
    assert m.Wq == pytest.approx(0.5)


def test_as_dict_keys():
    assert set(mm1_metrics(40, 50).as_dict()) == {"rho", "L", "Lq", "W", "Wq", "p0"}


@pytest.mark.parametrize("lam,mu", [(1, 2), (40, 50), (0.1, 0.11), (999, 1000), (3.5, 7)])
def test_littles_law(lam, mu):
    m = mm1_metrics(lam, mu)
    assert m.L == pytest.approx(lam * m.W)
    assert m.Lq == pytest.approx(lam * m.Wq)


@pytest.mark.parametrize("lam,mu", [(1, 2), (40, 50), (0.1, 0.11), (999, 1000)])
def test_consistency_relations(lam, mu):
    m = mm1_metrics(lam, mu)
    assert m.L == pytest.approx(m.Lq + m.rho)
    assert m.W == pytest.approx(m.Wq + 1 / mu)


def test_metrics_grow_toward_saturation():
    values = [mm1_metrics(lam, 50).L for lam in (10, 25, 40, 45, 49)]
    assert values == sorted(values)


@pytest.mark.parametrize("lam", [0, -1, -0.5])
def test_invalid_lambda(lam):
    with pytest.raises(QueueValidationError):
        mm1_metrics(lam, 50)


@pytest.mark.parametrize("mu", [0, -1])
def test_invalid_mu(mu):
    with pytest.raises(QueueValidationError):
        mm1_metrics(40, mu)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf, "40", None, True])
def test_non_numeric_or_non_finite(bad):
    with pytest.raises(QueueValidationError):
        mm1_metrics(bad, 50)
    with pytest.raises(QueueValidationError):
        mm1_metrics(40, bad)


@pytest.mark.parametrize("lam,mu", [(50, 50), (60, 50)])
def test_unstable_system(lam, mu):
    with pytest.raises(UnstableSystemError) as exc:
        mm1_metrics(lam, mu)
    assert "λ < μ" in str(exc.value)


def test_unstable_is_a_validation_error():
    assert issubclass(UnstableSystemError, QueueValidationError)
