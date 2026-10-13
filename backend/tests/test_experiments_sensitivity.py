"""Análise de sensibilidade (núcleo, sem passar pela API)."""

import pytest

from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.experiments.sensitivity import change_pct, run_sensitivity


def by_name(result):
    return {p.name: p for p in result.parameters}


def test_parameters_follow_the_model():
    assert [p.name for p in run_sensitivity("mm1", 40, 50).parameters] == ["lambda", "mu"]
    assert [p.name for p in run_sensitivity("mmc", 8, 1, servers=10).parameters] == ["lambda", "mu", "servers"]
    assert [p.name for p in run_sensitivity("mm1k", 12, 10, capacity=5).parameters] == ["lambda", "mu", "capacity"]
    full = run_sensitivity("mmck", 25, 10, servers=3, capacity=6)
    assert [p.name for p in full.parameters] == ["lambda", "mu", "servers", "capacity"]


def test_percent_and_unit_perturbations():
    params = by_name(run_sensitivity("mmck", 25, 10, servers=3, capacity=6, delta_pct=10))
    assert (params["lambda"].low.value, params["lambda"].high.value) == (22.5, 27.5)
    assert params["lambda"].perturbation == "percent"
    assert (params["servers"].low.value, params["servers"].high.value) == (2, 4)
    assert (params["capacity"].low.value, params["capacity"].high.value) == (5, 7)
    assert params["servers"].perturbation == "units"


def test_mm1_waiting_time_changes_match_the_closed_form():
    lam_effect = by_name(run_sensitivity("mm1", 40, 50, delta_pct=10))["lambda"].effects["W"]
    w = lambda lam: 1 / (50 - lam)
    assert lam_effect.high_change_pct == pytest.approx((w(44) / w(40) - 1) * 100)
    assert lam_effect.low_change_pct == pytest.approx((w(36) / w(40) - 1) * 100)
    assert lam_effect.elasticity == pytest.approx(((w(44) - w(36)) / w(40)) / 0.2)


def test_sensitivity_grows_near_saturation():
    far = by_name(run_sensitivity("mm1", 10, 50))["lambda"].effects["W"].elasticity
    near = by_name(run_sensitivity("mm1", 45, 50))["lambda"].effects["W"].elasticity
    assert near > 5 * far


def test_signs_make_sense_for_a_finite_system():
    params = by_name(run_sensitivity("mmck", 25, 10, servers=3, capacity=6))
    assert params["servers"].effects["p_block"].high_change_pct < 0     # mais servidores, menos recusas
    assert params["capacity"].effects["p_block"].high_change_pct < 0   # mais espaço, menos recusas
    assert params["capacity"].effects["W"].high_change_pct > 0         # ... e mais espera
    assert params["lambda"].effects["p_block"].high_change_pct > 0
    assert params["mu"].effects["W"].elasticity < 0                    # servidor mais rápido, menos tempo


def test_a_side_that_becomes_unstable_is_flagged_without_failing():
    effect = by_name(run_sensitivity("mm1", 40, 50, delta_pct=25))["lambda"]
    assert effect.high.status == "unstable" and effect.high.metrics is None
    assert effect.effects["W"].high_change_pct is None and effect.effects["W"].elasticity is None
    assert effect.effects["W"].low_change_pct is not None      # o outro lado continua


def test_removing_a_server_can_be_unstable_or_invalid():
    unstable = by_name(run_sensitivity("mmc", 8, 1, servers=9))["servers"]
    assert unstable.low.status == "unstable" and unstable.high.status == "ok"
    invalid = by_name(run_sensitivity("mmc", 0.5, 1, servers=1))["servers"]
    assert invalid.low.status == "invalid" and invalid.low.metrics is None


def test_capacity_below_servers_is_invalid():
    capacity = by_name(run_sensitivity("mmck", 25, 10, servers=3, capacity=3))["capacity"]
    assert capacity.low.status == "invalid"        # K = 2 < c = 3
    assert capacity.high.status == "ok"


def test_zero_base_metric_does_not_divide_by_zero():
    # No M/M/c, p_block é sempre 0.
    effect = by_name(run_sensitivity("mmc", 0.5, 1, servers=2))["lambda"].effects["p_block"]
    assert effect.low_change_pct == 0.0 and effect.high_change_pct == 0.0
    assert effect.elasticity is None


def test_change_pct():
    assert change_pct(110, 100) == pytest.approx(10)
    assert change_pct(90, 100) == pytest.approx(-10)
    assert change_pct(-5, -10) == pytest.approx(50)   # subiu 5 em relação a |-10|
    assert change_pct(0, 0) == 0.0
    assert change_pct(1, 0) is None


def test_base_point_must_be_stable():
    with pytest.raises(UnstableSystemError) as info:
        run_sensitivity("mm1", 60, 50)
    assert info.value.field == "lambda"


@pytest.mark.parametrize("kwargs,field", [
    (dict(model="mm1", lam=40, mu=50, delta_pct=0), "delta_pct"),
    (dict(model="mm1", lam=40, mu=50, delta_pct=51), "delta_pct"),
    (dict(model="mm1", lam=40, mu=50, delta_pct=-5), "delta_pct"),
    (dict(model="mmc", lam=40, mu=50), "servers"),
    (dict(model="mm1k", lam=40, mu=50), "capacity"),
    (dict(model="mmck", lam=1, mu=1, servers=4, capacity=2), "capacity"),
    (dict(model="mm1", lam=-1, mu=50), "lambda"),
    (dict(model="mm1", lam=1, mu=0), "mu"),
    (dict(model="nope", lam=1, mu=2), "model"),
])
def test_invalid_inputs_name_the_field(kwargs, field):
    with pytest.raises(QueueValidationError) as info:
        run_sensitivity(**kwargs)
    assert info.value.field == field
