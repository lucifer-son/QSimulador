"""Experimentos do serviço geral (M/G/1): varredura, sensibilidade e comparação de distribuições."""

import math

import pytest
from fastapi.testclient import TestClient

from app.domain.service.distributions import CATALOG, build_distribution
from app.domain.validation.errors import QueueValidationError
from app.experiments.mg1 import (
    run_mg1_sensitivity, run_mg1_sweep, run_services_comparison, service_at,
    sweepable_variables_mg1,
)
from app.experiments.sweep import SimulationSettings
from app.main import app

client = TestClient(app)
SWEEP, SENS, SERVICES = "/api/experiments/sweep", "/api/experiments/sensitivity", "/api/experiments/services"
LOGNORMAL = {"distribution": "lognormal", "mean": 0.02, "cv": 1.0}


def pk_wq(lam, mean, cv):
    """Pollaczek-Khinchine: Wq = λ·E[S²] / (2(1 − ρ)), com E[S²] = E[S]²(1 + CV²)."""
    rho = lam * mean
    return lam * mean**2 * (1 + cv**2) / (2 * (1 - rho))


# ---------- varredura: CV (a variabilidade do serviço) ----------

def test_cv_sweep_follows_pollaczek_khinchine():
    result = run_mg1_sweep("lognormal", {"mean": 0.02, "cv": 1.0}, "cv", 0.5, 2.0, 0.5, lam=25.0)
    assert [p.value for p in result.points] == [0.5, 1.0, 1.5, 2.0]
    for p in result.points:
        assert p.status == "ok"
        assert p.metrics["Wq"] == pytest.approx(pk_wq(25.0, 0.02, p.value))
        assert p.metrics["rho"] == pytest.approx(0.5)            # a média não muda
        assert p.offered_utilization == pytest.approx(0.5)
    assert result.model == "mg1" and result.variable == "cv"
    assert result.fixed == {"lambda": 25.0, "mu": pytest.approx(50.0)}
    assert result.service["distribution"] == "lognormal"


def test_cv_sweep_with_weibull_keeps_the_mean():
    result = run_mg1_sweep("weibull", {"mean": 0.02, "cv": 0.8}, "cv", 0.5, 1.5, 0.5, lam=25.0)
    assert all(p.metrics["Wq"] == pytest.approx(pk_wq(25.0, 0.02, p.value)) for p in result.points)


def test_k_sweep_gives_cv_one_over_sqrt_k():
    result = run_mg1_sweep("erlang", {"mean": 0.02, "k": 4}, "k", 1, 4, 1, lam=25.0)
    assert [p.value for p in result.points] == [1, 2, 3, 4]
    for p in result.points:
        assert p.metrics["Wq"] == pytest.approx(pk_wq(25.0, 0.02, 1 / math.sqrt(p.value)))
    assert result.points[0].metrics["Wq"] == pytest.approx(0.02)   # k = 1 é o M/M/1


def test_cv_out_of_range_marks_only_that_point_invalid():
    result = run_mg1_sweep("lognormal", {"mean": 0.02, "cv": 1.0}, "cv", 5, 15, 5, lam=25.0)
    assert [p.status for p in result.points] == ["ok", "ok", "invalid"]    # CV máximo é 10
    assert "cv" in result.points[2].message and result.points[2].metrics is None


@pytest.mark.parametrize("distribution", ["deterministic", "exponential", "uniform", "triangular", "truncated_normal"])
def test_shape_variables_only_exist_where_they_make_sense(distribution):
    assert sweepable_variables_mg1(distribution) == ("lambda", "mu")
    with pytest.raises(QueueValidationError) as error:
        run_mg1_sweep(distribution, {"mean": 0.02}, "cv", 0.5, 1.5, 0.5, lam=25.0)
    assert error.value.field == "variable"


# ---------- varredura: λ e μ ----------

def test_lambda_sweep_flags_unstable_points_and_keeps_going():
    result = run_mg1_sweep("deterministic", {"mean": 0.02}, "lambda", 10, 60, 10)
    assert [p.status for p in result.points] == ["ok", "ok", "ok", "ok", "unstable", "unstable"]
    assert result.points[0].metrics["Wq"] == pytest.approx(pk_wq(10.0, 0.02, 0.0))   # M/D/1
    assert result.fixed == {"mu": pytest.approx(50.0), "cv": 0.0}
    assert result.points[4].offered_utilization == pytest.approx(1.0)
    assert result.points[5].offered_utilization == pytest.approx(1.2)


def test_mu_sweep_rescales_the_service_and_keeps_the_cv():
    result = run_mg1_sweep("lognormal", {"mean": 0.02, "cv": 1.5}, "mu", 40, 80, 20, lam=25.0)
    for p in result.points:
        assert p.metrics["Wq"] == pytest.approx(pk_wq(25.0, 1 / p.value, 1.5))
    assert result.fixed == {"lambda": 25.0, "cv": pytest.approx(1.5)}


@pytest.mark.parametrize("spec", CATALOG, ids=lambda s: s.key)
def test_mu_sweep_preserves_cv_for_every_distribution(spec):
    base = build_distribution(spec.key, spec.example)
    scaled = service_at(spec.key, spec.example, "mu", 2 * base.mu)       # serviço duas vezes mais rápido
    assert scaled.mean == pytest.approx(base.mean / 2)
    assert scaled.cv == pytest.approx(base.cv)


def test_service_may_be_given_by_rate_instead_of_mean():
    by_mean = run_mg1_sweep("exponential", {"mean": 0.02}, "lambda", 10, 30, 10)
    by_rate = run_mg1_sweep("exponential", {"mu": 50.0}, "lambda", 10, 30, 10)
    assert [p.metrics for p in by_mean.points] == [p.metrics for p in by_rate.points]


def test_missing_lambda_when_not_swept_is_a_validation_error():
    with pytest.raises(QueueValidationError) as error:
        run_mg1_sweep("lognormal", {"mean": 0.02, "cv": 1.0}, "cv", 1, 2, 1)
    assert error.value.field == "lambda"


# ---------- simulação por ponto ----------

def test_simulation_covers_each_stable_point_with_the_common_seed():
    settings = SimulationSettings(simulation_time=2000, replications=5, warmup_time=100, seed=7)
    result = run_mg1_sweep("lognormal", {"mean": 0.02, "cv": 1.0}, "cv", 0.5, 1.5, 0.5, lam=25.0, simulation=settings)
    assert result.simulation.seed == 7
    for p in result.points:
        assert p.simulation is not None
        assert p.simulation["Wq"].mean == pytest.approx(p.metrics["Wq"], rel=0.25)
    again = run_mg1_sweep("lognormal", {"mean": 0.02, "cv": 1.0}, "cv", 0.5, 1.5, 0.5, lam=25.0, simulation=settings)
    assert [p.simulation["Wq"].mean for p in again.points] == [p.simulation["Wq"].mean for p in result.points]


def test_unstable_points_are_not_simulated():
    settings = SimulationSettings(simulation_time=200, replications=3, seed=1)
    result = run_mg1_sweep("deterministic", {"mean": 0.02}, "lambda", 40, 60, 10, lam=None, simulation=settings)
    assert [p.simulation is not None for p in result.points] == [True, False, False]


# ---------- sensibilidade ----------

def test_sensitivity_lists_the_shape_parameter_of_the_distribution():
    names = lambda d, v: [p.name for p in run_mg1_sensitivity(d, v, 25.0).parameters]   # noqa: E731
    assert names("lognormal", {"mean": 0.02, "cv": 1.5}) == ["lambda", "mu", "cv"]
    assert names("erlang", {"mean": 0.02, "k": 4}) == ["lambda", "mu", "k"]
    assert names("deterministic", {"mean": 0.02}) == ["lambda", "mu"]


def test_sensitivity_to_cv_matches_the_closed_form():
    result = run_mg1_sensitivity("lognormal", {"mean": 0.02, "cv": 1.0}, 25.0, delta_pct=10)
    cv = next(p for p in result.parameters if p.name == "cv")
    assert (cv.low.value, cv.high.value) == (pytest.approx(0.9), pytest.approx(1.1))
    base = pk_wq(25.0, 0.02, 1.0)
    assert cv.effects["Wq"].high_change_pct == pytest.approx((pk_wq(25.0, 0.02, 1.1) / base - 1) * 100)
    assert cv.effects["rho"].high_change_pct == pytest.approx(0.0)         # o CV não muda a utilização
    assert result.base["cv"] == pytest.approx(1.0) and result.service["distribution"] == "lognormal"


def test_sensitivity_to_lambda_and_mu_are_opposite():
    result = run_mg1_sensitivity("lognormal", {"mean": 0.02, "cv": 1.5}, 25.0)
    lam, mu = result.parameters[0], result.parameters[1]
    assert lam.effects["Wq"].elasticity > 1 and mu.effects["Wq"].elasticity < -1


def test_sensitivity_erlang_k_is_in_units_and_k_one_side_may_be_invalid():
    result = run_mg1_sensitivity("erlang", {"mean": 0.02, "k": 1}, 25.0)
    k = result.parameters[2]
    assert (k.perturbation, k.low.status, k.high.status) == ("units", "invalid", "ok")
    assert k.effects["Wq"].elasticity is None


def test_sensitivity_base_point_must_be_stable():
    with pytest.raises(QueueValidationError):
        run_mg1_sensitivity("exponential", {"mean": 0.02}, 60.0)


# ---------- comparação de distribuições ----------

def test_services_comparison_orders_waiting_by_variability():
    specs = [("deterministic", {"mean": 0.02}), ("exponential", {"mean": 0.02}), ("lognormal", {"mean": 0.02, "cv": 1.5})]
    result = run_services_comparison(specs, 10, 40, 10)
    assert [s.service["distribution"] for s in result.series] == ["deterministic", "exponential", "lognormal"]
    for i in range(4):
        wq = [s.points[i].metrics["Wq"] for s in result.series]
        assert wq[0] < wq[1] < wq[2]
    assert wq[0] == pytest.approx(pk_wq(40.0, 0.02, 0.0))


def test_services_comparison_needs_two_to_eight_distributions():
    one = [("exponential", {"mean": 0.02})]
    with pytest.raises(QueueValidationError):
        run_services_comparison(one, 10, 40, 10)
    with pytest.raises(QueueValidationError):
        run_services_comparison(one * 9, 10, 40, 10)


def test_services_with_different_means_saturate_at_different_loads():
    specs = [("exponential", {"mean": 0.02}), ("exponential", {"mean": 0.04})]
    result = run_services_comparison(specs, 10, 40, 10)
    assert [p.status for p in result.series[0].points] == ["ok", "ok", "ok", "ok"]
    assert [p.status for p in result.series[1].points] == ["ok", "ok", "unstable", "unstable"]


# ---------- HTTP ----------

def post(url, **body):
    return client.post(url, json=body)


def test_http_sweep_mg1_with_service_object():
    r = post(SWEEP, model="mg1", variable="cv", start=0.5, end=1.5, step=0.5,
             **{"lambda": 25}, service=LOGNORMAL)
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "mg1" and body["service"]["distribution"] == "lognormal"
    assert [p["value"] for p in body["points"]] == [0.5, 1.0, 1.5]
    assert len(body["points"][0]["metrics"]) == 7


def test_http_sweep_mg1_with_simulation():
    r = post(SWEEP, model="mg1", variable="lambda", start=10, end=30, step=10, service=LOGNORMAL,
             simulate=True, simulation_time=300, replications=3, seed=1)
    assert r.status_code == 200
    assert r.json()["simulation"]["seed"] == 1
    assert all(p["simulation"]["Wq"]["mean"] > 0 for p in r.json()["points"])


def test_http_sweep_mg1_requires_service():
    r = post(SWEEP, model="mg1", variable="lambda", start=10, end=30, step=10)
    assert r.status_code == 422
    assert [f["field"] for f in r.json()["fields"]] == ["service"]


def test_http_sweep_mg1_rejects_cv_for_an_exponential_service():
    r = post(SWEEP, model="mg1", variable="cv", start=1, end=2, step=1, **{"lambda": 25},
             service={"distribution": "exponential", "mean": 0.02})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "variable"


def test_http_sweep_markov_models_ignore_service_and_still_work():
    r = post(SWEEP, model="mm1", variable="lambda", start=10, end=30, step=10, mu=50, service=LOGNORMAL)
    assert r.status_code == 200 and r.json()["service"] is None


def test_http_sweep_markov_does_not_accept_the_shape_variables():
    r = post(SWEEP, model="mm1", variable="cv", start=1, end=2, step=1, **{"lambda": 25}, mu=50)
    assert r.status_code == 422


def test_http_sensitivity_mg1():
    r = post(SENS, model="mg1", **{"lambda": 25}, service={"distribution": "weibull", "mean": 0.02, "cv": 0.8})
    assert r.status_code == 200
    assert [p["name"] for p in r.json()["parameters"]] == ["lambda", "mu", "cv"]
    assert r.json()["service"]["label"] == "Weibull"


def test_http_sensitivity_markov_still_requires_mu():
    r = post(SENS, model="mm1", **{"lambda": 25})
    assert r.status_code == 422 and r.json()["fields"][0]["field"] == "mu"


def test_http_sensitivity_unstable_base_is_422():
    r = post(SENS, model="mg1", **{"lambda": 80}, service={"distribution": "exponential", "mean": 0.02})
    assert r.status_code == 422 and r.json()["code"] == "unstable_system"


def test_http_services_comparison():
    r = post(SERVICES, start=10, end=40, step=10, services=[
        {"distribution": "deterministic", "mean": 0.02},
        {"distribution": "exponential", "mu": 50.0},
        {"distribution": "uniform", "min": 0.01, "max": 0.03},
    ])
    assert r.status_code == 200
    series = r.json()["series"]
    assert [s["service"]["label"] for s in series] == ["Determinística (M/D/1)", "Exponencial", "Uniforme"]
    assert all(len(s["points"]) == 4 for s in series)


def test_http_services_comparison_validates_each_distribution_and_the_count():
    one = post(SERVICES, start=10, end=40, step=10, services=[{"distribution": "exponential", "mean": 0.02}])
    assert one.status_code == 422 and one.json()["fields"][0]["field"] == "services"
    bad = post(SERVICES, start=10, end=40, step=10, services=[
        {"distribution": "exponential", "mean": 0.02}, {"distribution": "lognormal", "mean": 0.02},
    ])
    assert bad.status_code == 422 and bad.json()["fields"][0]["field"] == "cv"
