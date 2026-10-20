"""M/G/c (Allen–Cunneen): casos exatos, propriedades, avisos de faixa e simulação."""

import pytest

from app.analysis.comparison_phase10 import MGC_METRIC_NAMES, compare_mgc
from app.analytical.mg1 import mg1_metrics
from app.analytical.mgc import WARN_CV, WARN_RHO, is_exact, mgc_metrics, validity_warnings
from app.analytical.mmck import mmc_metrics
from app.domain.models.naming import multi_server_service_model_name
from app.domain.service.distributions import CATALOG, build_distribution
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.simulation.mgc import simulate_mgc

EXP = build_distribution("exponential", {"mean": 0.1})


def lognormal(cv, mean=0.1):
    return build_distribution("lognormal", {"mean": mean, "cv": cv})


# ---------- casos em que a aproximação é exata ----------

@pytest.mark.parametrize("lam, c", [(5, 1), (80, 10), (45, 5), (190, 20)])
def test_cv_one_reproduces_mmc(lam, c):
    exact = mmc_metrics(lam, 10.0, c)
    m = mgc_metrics(lam, EXP, c)
    for name in ("rho", "L", "Lq", "W", "Wq", "p_wait"):
        assert getattr(m, name) == pytest.approx(getattr(exact, name), rel=1e-10), name
    assert m.throughput == lam


@pytest.mark.parametrize("spec", CATALOG, ids=lambda s: s.key)
def test_one_server_reproduces_pollaczek_khinchine_for_every_distribution(spec):
    service = build_distribution(spec.key, spec.example)
    lam = 0.6 / service.mean
    m, pk = mgc_metrics(lam, service, 1), mg1_metrics(lam, service)
    for name in ("rho", "L", "Lq", "W", "Wq"):
        assert getattr(m, name) == pytest.approx(getattr(pk, name), rel=1e-10), name


def test_lq_scales_with_one_plus_cv_squared_over_two():
    base = mgc_metrics(80, EXP, 10).Lq
    for cv in (0.25, 0.5, 1.5, 2.5):
        assert mgc_metrics(80, lognormal(cv), 10).Lq == pytest.approx(base * (1 + cv**2) / 2)


def test_more_variable_service_waits_longer_at_the_same_load():
    waits = [mgc_metrics(80, build_distribution("deterministic", {"mean": 0.1}), 10).Wq]
    waits += [mgc_metrics(80, lognormal(cv), 10).Wq for cv in (0.5, 1.0, 2.0)]
    assert waits == sorted(waits) and waits[0] < waits[-1]


@pytest.mark.parametrize("c", [1, 2, 5, 12])
def test_littles_law_and_utilization(c):
    service = lognormal(1.3, mean=0.05)
    lam = 0.75 * c / service.mean
    m = mgc_metrics(lam, service, c)
    assert m.L == pytest.approx(lam * m.W) and m.Lq == pytest.approx(lam * m.Wq)
    assert m.W == pytest.approx(m.Wq + service.mean)
    assert m.rho == pytest.approx(0.75)


def test_more_servers_at_fixed_load_reduce_waiting():
    service = lognormal(1.5)
    waits = [mgc_metrics(c * 8.0, service, c).Wq for c in (1, 2, 4, 8, 16)]   # ρ = 0.8 em todos
    assert all(x > y for x, y in zip(waits, waits[1:]))


# ---------- validação ----------

def test_unstable_system_is_rejected_with_rho_in_the_message():
    with pytest.raises(UnstableSystemError) as error:
        mgc_metrics(100, EXP, 10)                    # ρ = 1
    assert "ρ" in str(error.value) and error.value.field == "lambda"
    with pytest.raises(UnstableSystemError):
        simulate_mgc(120, EXP, 10, 100)


@pytest.mark.parametrize("lam, servers, field", [(0, 3, "λ"), (-5, 3, "λ"), (5, 0, "servers"), (5, 2.5, "servers"), (5, 1001, "servers"), (5, True, "servers")])
def test_invalid_parameters(lam, servers, field):
    with pytest.raises(QueueValidationError) as error:
        mgc_metrics(lam, EXP, servers)
    assert field in (error.value.field or "") or field in str(error.value)


def test_model_names():
    assert multi_server_service_model_name("deterministic", 3) == "M/D/3"
    assert multi_server_service_model_name("lognormal", 10) == "M/G/10"


# ---------- exatidão e avisos de faixa ----------

def test_exact_flag():
    assert is_exact(lognormal(1.5), 1) and is_exact(EXP, 8) and is_exact(lognormal(1.0), 4)
    assert not is_exact(lognormal(1.5), 2) and not is_exact(build_distribution("deterministic", {"mean": 0.1}), 3)


def test_warnings_for_high_utilization_and_high_variability():
    assert validity_warnings(0.5, 1.5, 4) == []
    assert len(validity_warnings(WARN_RHO + 0.01, 1.5, 4)) == 1
    assert len(validity_warnings(0.5, WARN_CV + 0.5, 4)) == 1
    assert len(validity_warnings(0.95, 3.0, 4)) == 2
    assert validity_warnings(0.95, 3.0, 1) == []          # com um servidor é exato (P-K)
    assert validity_warnings(0.95, 1.0, 4) == []          # CV = 1 é o M/M/c


# ---------- simulação ----------

def test_simulation_is_reproducible_and_seed_dependent():
    kwargs = dict(servers=4, simulation_time=300, replications=3, warmup_time=20)
    a = simulate_mgc(30, lognormal(1.2), seed=5, **kwargs)
    b = simulate_mgc(30, lognormal(1.2), seed=5, **kwargs)
    c = simulate_mgc(30, lognormal(1.2), seed=6, **kwargs)
    assert a.summary["Wq"].mean == b.summary["Wq"].mean != c.summary["Wq"].mean
    assert a.service["distribution"] == "lognormal" and a.servers == 4


@pytest.mark.parametrize("distribution, values, seed", [
    ("exponential", {"mean": 0.1}, 21),
    ("lognormal", {"mean": 0.1, "cv": 0.5}, 22),
])
def test_simulation_matches_the_exact_cases(distribution, values, seed):
    # Com 1 servidor (P-K) a aproximação é exata, para qualquer distribuição.
    service = build_distribution(distribution, values)
    r = compare_mgc(7.0, service, 1, simulation_time=4000, replications=10, warmup_time=200, seed=seed)
    assert r.all_within_ci is True and r.max_relative_error_pct < 8


def test_exponential_service_with_many_servers_matches_erlang_c():
    r = compare_mgc(80, EXP, 10, simulation_time=1500, replications=10, warmup_time=100, seed=31)
    assert r.all_within_ci is True
    assert r.metrics["p_wait"].relative_error_pct < 3


@pytest.mark.parametrize("cv", [0.0, 0.5, 1.5])
def test_approximation_error_is_small_in_the_comfortable_range(cv):
    service = build_distribution("deterministic", {"mean": 0.1}) if cv == 0 else lognormal(cv)
    r = compare_mgc(70, service, 10, simulation_time=2000, replications=10, warmup_time=100, seed=40 + int(cv * 10))
    assert r.metrics["Wq"].relative_error_pct < 25          # erro da aproximação, não da simulação
    assert r.metrics["rho"].within_ci and r.metrics["throughput"].within_ci


def test_comparison_covers_the_seven_metrics_without_p0():
    r = compare_mgc(40, EXP, 5, simulation_time=300, replications=3, seed=1)
    assert tuple(r.metrics) == MGC_METRIC_NAMES and "p0" not in r.metrics
    assert r.service["distribution"] == "exponential"
