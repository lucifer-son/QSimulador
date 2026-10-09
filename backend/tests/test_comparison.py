import json

import pytest

from app.analysis.comparison import compare_metrics, compare_mm1, relative_error_pct
from app.analytical.mm1 import mm1_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.simulation.mm1 import simulate_mm1
from app.simulation.results import METRIC_NAMES, MetricSummary


def summary(mean, low, high, n=10):
    return MetricSummary(mean=mean, std=0.1, ci_low=low, ci_high=high, n=n)


def full_summary(**overrides):
    base = {name: summary(1.0, 0.9, 1.1) for name in METRIC_NAMES}
    base.update(overrides)
    return base


ANALYTICAL = {name: 1.0 for name in METRIC_NAMES}


# ---------- erro relativo ----------

@pytest.mark.parametrize(
    "value,reference,expected",
    [(10, 8, 25.0), (6, 8, 25.0), (8, 8, 0.0), (0.0992, 0.1, 0.8), (1, -2, 150.0)],
)
def test_relative_error(value, reference, expected):
    assert relative_error_pct(value, reference) == pytest.approx(expected)


def test_relative_error_with_zero_reference():
    assert relative_error_pct(0, 0) == 0.0
    assert relative_error_pct(1, 0) is None


# ---------- lógica de comparação (dados sintéticos) ----------

def test_value_inside_interval():
    c = compare_metrics(ANALYTICAL, full_summary())["rho"]
    assert c.within_ci is True
    assert c.absolute_error == pytest.approx(0.0)


def test_value_outside_interval():
    result = compare_metrics(ANALYTICAL, full_summary(L=summary(1.5, 1.4, 1.6)))["L"]
    assert result.within_ci is False
    assert result.absolute_error == pytest.approx(0.5)
    assert result.relative_error_pct == pytest.approx(50.0)


@pytest.mark.parametrize("low,high", [(1.0, 1.2), (0.8, 1.0)])
def test_interval_bounds_are_inclusive(low, high):
    c = compare_metrics(ANALYTICAL, full_summary(W=summary(1.1, low, high)))["W"]
    assert c.within_ci is True


def test_no_interval_gives_none():
    no_ci = MetricSummary(mean=0.9, std=None, ci_low=None, ci_high=None, n=1)
    c = compare_metrics(ANALYTICAL, full_summary(Lq=no_ci))["Lq"]
    assert c.within_ci is None
    assert c.ci_low is None and c.ci_high is None
    assert c.relative_error_pct == pytest.approx(10.0)  # o erro continua calculado


def test_covers_all_metrics():
    assert set(compare_metrics(ANALYTICAL, full_summary())) == set(METRIC_NAMES)


# ---------- fluxo completo ----------

@pytest.fixture(scope="module")
def result():
    return compare_mm1(1, 2, 5000, replications=10, warmup_time=200, seed=42)


def test_analytical_side_matches_model(result):
    exact = mm1_metrics(1, 2)
    for name in ("rho", "L", "Lq", "W", "Wq"):
        assert result.metrics[name].analytical == pytest.approx(getattr(exact, name))


def test_throughput_reference_is_lambda(result):
    assert result.metrics["throughput"].analytical == pytest.approx(1.0)


def test_simulated_side_matches_simulation(result):
    sim = simulate_mm1(1, 2, 5000, replications=10, warmup_time=200, seed=42)
    for name in METRIC_NAMES:
        assert result.metrics[name].simulated_mean == sim.summary[name].mean
        assert result.metrics[name].ci_low == sim.summary[name].ci_low


def test_errors_are_small_for_a_long_run(result):
    # Tolerância ampla (pior erro observado entre sementes ≈ 5%).
    assert result.max_relative_error_pct < 10
    assert isinstance(result.all_within_ci, bool)


def test_metadata_is_echoed(result):
    assert (result.lam, result.mu, result.seed) == (1.0, 2.0, 42)
    assert result.replications == 10 and result.warmup_time == 200
    assert result.confidence_level == 0.95


def test_single_replication_is_rejected():
    from app.domain.validation.errors import QueueValidationError

    with pytest.raises(QueueValidationError) as exc:
        compare_mm1(1, 2, 300, replications=1, seed=1)
    assert exc.value.field == "replications"


def test_random_seed_is_reported_and_reproducible():
    a = compare_mm1(1, 2, 300, replications=2)
    b = compare_mm1(1, 2, 300, replications=2, seed=a.seed)
    assert a.metrics == b.metrics


def test_result_is_json_serializable(result):
    json.dumps(result.as_dict())


def test_unstable_system_is_rejected():
    with pytest.raises(UnstableSystemError):
        compare_mm1(2, 2, 100)


def test_invalid_settings_are_rejected():
    with pytest.raises(QueueValidationError):
        compare_mm1(1, 2, 100, replications=0)


def test_values_are_native_python_types(result):
    # numpy.bool_ não é serializável em JSON; garantimos bool nativo.
    for m in result.metrics.values():
        assert type(m.within_ci) is bool
    assert type(result.all_within_ci) is bool
