"""Curva Wq × λ (Fase 13, RFC-24): reaproveita a varredura da Fase 6."""

import pytest

from app.analysis.sensitivity_curve import wq_vs_lambda
from app.analytical.mm1 import mm1_metrics
from app.analytical.mmck import mmc_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.experiments.sweep import run_sweep


def test_mm1_curve_is_the_closed_form_and_marks_the_current_point():
    c = wq_vs_lambda("mm1", 8, mu=10)
    assert c.points[c.current_index].value == 8
    assert c.current.wq == pytest.approx(mm1_metrics(8, 10).Wq) == pytest.approx(0.4)
    assert c.points[0].value == pytest.approx(4.0)           # λ·(1 − 0,5)
    for p in c.points:
        assert p.wq == pytest.approx(mm1_metrics(p.value, 10).Wq)
    assert [p.wq for p in c.points] == sorted(p.wq for p in c.points)    # Wq cresce com λ


def test_it_is_the_phase6_sweep_not_a_new_calculation():
    c = wq_vs_lambda("mmc", 15, mu=10, servers=2, points=21)
    sweep = run_sweep("mmc", "lambda", 7.5, c.points[-1].value, 0.75, mu=10, servers=2)
    assert [p.value for p in c.points] == [p.value for p in sweep.points]
    assert [p.wq for p in c.points] == [p.metrics["Wq"] for p in sweep.points]


def test_infinite_queue_stops_before_saturation():
    c = wq_vs_lambda("mm1", 8, mu=10, span=0.9)
    assert c.stability_limit == pytest.approx(9.9)
    assert max(p.value for p in c.points) <= 9.9 and all(p.status == "ok" for p in c.points)


def test_current_point_above_the_limit_is_kept():
    c = wq_vs_lambda("mm1", 9.95, mu=10)
    assert c.points[-1].value == pytest.approx(9.95) and c.points[c.current_index].value == pytest.approx(9.95)


def test_finite_capacity_goes_beyond_c_mu_and_saturates():
    c = wq_vs_lambda("mmck", 15, mu=10, servers=2, capacity=6, span=0.9, points=21)
    assert c.stability_limit is None
    assert c.points[-1].value == pytest.approx(15 * 1.9) and c.points[-1].value > 20     # λ > c·μ, ainda estável
    assert all(p.status == "ok" for p in c.points)
    top = [p.wq for p in c.points][-4:]
    assert max(top) - min(top) < 0.2 * max(top)                # a curva se achata com K finito


def test_general_service_uses_the_general_sweep():
    c = wq_vs_lambda("mgc", 15, servers=2, distribution="lognormal", service_values={"mean": 0.1, "cv": 1.5}, points=21)
    assert c.service["label"] == "Lognormal"
    assert c.points[c.current_index].wq == pytest.approx(c.current.wq)
    mm = wq_vs_lambda("mgc", 15, servers=2, distribution="exponential", service_values={"mean": 0.1}, points=21)
    assert mm.current.wq == pytest.approx(mmc_metrics(15, 10, 2).Wq)
    assert c.current.wq > mm.current.wq                        # CV > 1 espera mais


def test_errors():
    with pytest.raises(UnstableSystemError):
        wq_vs_lambda("mm1", 12, mu=10)
    for kwargs, field in [({"model": "erlangb", "mu": 10, "servers": 2}, "model"),
                          ({"model": "mm1", "mu": 10, "span": 0}, "span"),
                          ({"model": "mm1", "mu": 10, "span": 1.0}, "span"),
                          ({"model": "mm1", "mu": 10, "points": 2}, "points"),
                          ({"model": "mm1"}, "mu"),
                          ({"model": "mmc", "mu": 10}, "servers"),
                          ({"model": "mg1"}, "service")]:
        with pytest.raises(QueueValidationError) as e:
            wq_vs_lambda(lam=8, **kwargs)
        assert e.value.field == field, kwargs
