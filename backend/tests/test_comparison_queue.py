import json

import pytest

from app.analysis.comparison import compare_metrics, compare_queue
from app.analytical.mmck import queue_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.simulation.mmck import simulate_mmck
from app.simulation.results import MetricSummary, QUEUE_METRIC_NAMES


def summary(mean, low, high):
    return MetricSummary(mean=mean, std=0.1, ci_low=low, ci_high=high, n=10)


def test_compare_metrics_accepts_custom_metric_list():
    result = compare_metrics({"p_block": 0.10, "L": 2.0},
                             {"p_block": summary(0.12, 0.09, 0.15), "L": summary(2.1, 1.9, 2.3)},
                             metric_names=("p_block",))
    assert list(result) == ["p_block"]
    assert result["p_block"].relative_error_pct == pytest.approx(20.0)
    assert result["p_block"].within_ci is True


def test_compare_metrics_default_is_unchanged():
    names = ("rho", "L", "Lq", "W", "Wq", "throughput")
    ref = {n: 1.0 for n in names}
    out = compare_metrics(ref, {n: summary(1.0, 0.9, 1.1) for n in names})
    assert tuple(out) == names


@pytest.mark.parametrize("lam,mu,c,K", [(1.5, 1, 2, None), (1.2, 1, 1, 5), (2.5, 1, 3, 6)])
def test_compare_queue_is_consistent_with_its_parts(lam, mu, c, K):
    kwargs = dict(simulation_time=400, replications=4, warmup_time=20, seed=3)
    cmp = compare_queue(lam, mu, c, K, **kwargs)
    sim = simulate_mmck(lam, mu, c, K, **kwargs)
    exact = queue_metrics(lam, mu, c, K).as_dict()

    assert tuple(cmp.metrics) == QUEUE_METRIC_NAMES
    for name, m in cmp.metrics.items():
        assert m.analytical == pytest.approx(exact[name])                 # lado analítico
        assert m.simulated_mean == sim.summary[name].mean                 # lado simulado
        assert m.ci_low == sim.summary[name].ci_low
        if exact[name] != 0:
            assert m.relative_error_pct == pytest.approx(abs(m.simulated_mean - exact[name]) / exact[name] * 100)
        if m.ci_low is not None:
            assert m.within_ci == (m.ci_low <= exact[name] <= m.ci_high)
    assert (cmp.servers, cmp.capacity, cmp.seed) == (c, K, 3)


def test_compare_queue_overall_fields():
    cmp = compare_queue(2.5, 1, 3, 6, 400, replications=4, warmup_time=20, seed=3)
    assert cmp.all_within_ci == all(m.within_ci for m in cmp.metrics.values())
    assert cmp.max_relative_error_pct == pytest.approx(max(m.relative_error_pct for m in cmp.metrics.values()))


def test_compare_queue_single_replication_has_no_verdict():
    cmp = compare_queue(2.5, 1, 3, 6, 300, replications=1, seed=1)
    assert cmp.all_within_ci is None
    assert all(m.within_ci is None for m in cmp.metrics.values())


def test_compare_queue_is_reproducible_and_serializable():
    a = compare_queue(1.5, 1, 2, None, 300, replications=3, seed=9)
    b = compare_queue(1.5, 1, 2, None, 300, replications=3, seed=9)
    assert a == b
    json.dumps(a.as_dict())


def test_compare_queue_validation():
    with pytest.raises(UnstableSystemError):
        compare_queue(2, 1, 2, None, 100)
    with pytest.raises(QueueValidationError):
        compare_queue(1, 1, 3, 2, 100)          # K < c
