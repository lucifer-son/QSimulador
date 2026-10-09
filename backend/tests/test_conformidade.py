"""Testes das divergências fechadas na auditoria de conformidade (RF-03, RF-06, RF-28, RF-31, RNF-12)."""

import math
import random
from fractions import Fraction
from math import factorial

import numpy as np
import pytest
from fastapi.testclient import TestClient
from scipy.special import gammaln

from app.analysis.comparison import compare_mm1, compare_queue
from app.analytical.mm1 import mm1_metrics
from app.analytical.mmck import mm1k_metrics, mmc_metrics, mmck_metrics
from app.domain.validation.errors import (
    InsufficientSampleError,
    QueueValidationError,
    UnstableSystemError,
)
from app.domain.validation.mm1 import validate_mm1_parameters
from app.domain.validation.mmck import validate_queue_parameters
from app.domain.validation.simulation import (
    MAX_EVENTS_PER_REPLICATION,
    MAX_EXPECTED_ARRIVALS,
    MAX_REPLICATIONS,
    MIN_REPLICATIONS,
    validate_simulation_settings,
)
from app.main import app
from app.simulation import mm1 as sim_mm1
from app.simulation import mmck as sim_mmck
from app.simulation.mm1 import simulate_mm1
from app.simulation.mmck import simulate_mmck

client = TestClient(app)


# =====================================================================
# RF-03 — P0 no cálculo analítico
# =====================================================================

class TestP0Analytical:
    def test_mm1_is_one_minus_rho(self):
        assert mm1_metrics(40, 50).p0 == pytest.approx(0.2)
        assert mm1_metrics(40, 50).p0 == pytest.approx(1 - mm1_metrics(40, 50).rho)

    @pytest.mark.parametrize("m, expected", [
        (lambda: mmc_metrics(1, 1, 2), 1 / 3),           # M/M/2 com λ = μ
        (lambda: mm1k_metrics(1, 1, 2), 1 / 3),          # M/M/1/2 com λ = μ: P_n = 1/3
        (lambda: mmck_metrics(1, 1, 2, 2), 0.4),         # M/M/2/2 com a = 1: 1 / 2,5
        (lambda: mmc_metrics(8, 1, 10), 1 / 3615.70),    # M/M/10, a = 8: Σ(n<10) aⁿ/n! = 2136,23 e termo final = 1479,47
    ])
    def test_known_values(self, m, expected):
        assert m().p0 == pytest.approx(expected, rel=1e-3)

    def test_single_server_utilization_is_one_minus_p0_even_with_blocking(self):
        # num único servidor, o servidor está ocupado exatamente quando o sistema não está vazio
        for lam, mu, K in [(1, 2, 5), (3, 2, 4), (10, 1, 7)]:
            m = mm1k_metrics(lam, mu, K)
            assert m.rho == pytest.approx(1 - m.p0)

    def test_matches_exact_fraction_arithmetic(self):
        rng = random.Random(11)
        for _ in range(150):
            c, K = rng.randint(1, 8), None
            mu = rng.choice([1, 2, 5])
            lam = round(rng.uniform(0.2, 2.5) * c * mu, 1)
            lam_f, mu_f = Fraction(lam).limit_denominator(10**6), Fraction(mu)
            K = c + rng.randint(0, 20)
            w = [Fraction(1)]
            for n in range(1, K + 1):
                w.append(w[-1] * lam_f / (min(n, c) * mu_f))
            exact = float(w[0] / sum(w))
            assert mmck_metrics(lam, mu, c, K).p0 == pytest.approx(exact, rel=1e-12)
        for _ in range(150):
            c = rng.randint(1, 20)
            mu = rng.choice([1, 2, 5])
            lam = round(rng.uniform(0.05, 0.97) * c * mu, 2)
            a, rho = Fraction(lam).limit_denominator(10**6) / mu, Fraction(lam).limit_denominator(10**6) / (c * mu)
            exact = float(1 / (sum(a**n / factorial(n) for n in range(c)) + a**c / (factorial(c) * (1 - rho))))
            assert mmc_metrics(lam, mu, c).p0 == pytest.approx(exact, rel=1e-12)

    def test_mmc_equals_the_finite_model_with_a_huge_capacity(self):
        big, ref = mmck_metrics(8, 1, 10, 100_000), mmc_metrics(8, 1, 10)
        assert big.p0 == pytest.approx(ref.p0, rel=1e-9)

    def test_erlang_c_identity(self):
        # C(c, a) = aᶜ / (c!·(1 − ρ)) · P0
        c, lam, mu = 12, 9, 1
        a, rho = lam / mu, lam / (c * mu)
        m = mmc_metrics(lam, mu, c)
        tail = math.exp(c * math.log(a) - gammaln(c + 1) - math.log(1 - rho))
        assert m.p_wait == pytest.approx(tail * m.p0, rel=1e-10)

    def test_numerically_stable_with_many_servers(self):
        m = mmc_metrics(450, 1, 500)
        assert math.isfinite(m.p0) and 0 < m.p0 < 1

    def test_p0_is_always_a_probability(self):
        rng = random.Random(3)
        for _ in range(100):
            c = rng.randint(1, 15)
            m = mmck_metrics(rng.uniform(0.1, 30), 1, c, c + rng.randint(0, 30))
            assert 0 < m.p0 <= 1


# =====================================================================
# RF-31 — P0 na simulação e na comparação
# =====================================================================

class TestP0Simulation:
    def test_deterministic_mm1_engine_measures_the_empty_fraction(self):
        # chegadas a cada 1,0 e serviço de 0,5: o sistema fica vazio metade do tempo
        r = sim_mm1.run_replication(1, 2, 1000, 0, np.random.default_rng(0), interarrival=lambda: 1.0, service=lambda: 0.5)
        assert r.p0 == pytest.approx(0.5, abs=0.01)

    def test_deterministic_generic_engine_measures_the_empty_fraction(self):
        r = sim_mmck.run_replication(1, 2, 1, None, 1000, 0, np.random.default_rng(0), interarrival=lambda: 1.0, service=lambda: 0.5)
        assert r.p0 == pytest.approx(0.5, abs=0.01)

    def test_overloaded_system_is_never_empty(self):
        for run in (
            lambda: sim_mm1.run_replication(2, 1, 100, 0, np.random.default_rng(0), interarrival=lambda: 0.5, service=lambda: 1.0),
            lambda: sim_mmck.run_replication(2, 1, 1, None, 100, 0, np.random.default_rng(0), interarrival=lambda: 0.5, service=lambda: 1.0),
        ):
            assert run().p0 < 0.02

    def test_warmup_excludes_the_initial_empty_period(self):
        # sem aquecimento, o início vazio infla P0; com aquecimento, só conta o regime medido
        r = sim_mm1.run_replication(1, 2, 1000, 100, np.random.default_rng(0), interarrival=lambda: 1.0, service=lambda: 0.5)
        assert r.observation_time == pytest.approx(900)
        assert r.p0 == pytest.approx(0.5, abs=0.01)

    def test_p0_and_utilization_are_complementary_for_one_server(self):
        r = sim_mm1.run_replication(1, 2, 2000, 100, np.random.default_rng(5))
        assert r.p0 + r.rho == pytest.approx(1.0)
        g = sim_mmck.run_replication(1, 2, 1, 5, 2000, 100, np.random.default_rng(5))
        assert g.p0 + g.rho == pytest.approx(1.0)

    def test_summaries_include_p0_in_both_engines(self):
        assert "p0" in simulate_mm1(1, 2, 300, replications=2, seed=1).summary
        assert "p0" in simulate_mmck(1, 1, 2, 5, 300, replications=2, seed=1).summary

    @pytest.mark.parametrize("comparison, tolerance", [
        (lambda: compare_mm1(1, 2, 3000, replications=10, warmup_time=100, seed=42), 0.04),
        (lambda: compare_queue(2.5, 1, 3, 6, 1500, replications=10, warmup_time=100, seed=42), 0.09),
        (lambda: compare_queue(1.5, 1, 2, None, 1500, replications=10, warmup_time=100, seed=42), 0.15),
    ])
    def test_simulated_p0_matches_the_analytical_value(self, comparison, tolerance):
        # tolerâncias calibradas: ~2x o pior erro em 20 sementes (1,9 %, 4,4 % e 7,5 %)
        m = comparison().metrics["p0"]
        assert m.simulated_mean == pytest.approx(m.analytical, rel=tolerance)

    def test_comparison_lists_p0_right_after_wq_as_in_the_specification(self):
        assert list(compare_mm1(1, 2, 200, replications=2, seed=1).metrics) == ["rho", "L", "Lq", "W", "Wq", "p0", "throughput"]
        assert list(compare_queue(1, 1, 2, 5, 200, replications=2, seed=1).metrics) == [
            "rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"]


# =====================================================================
# RF-06 e RNF-12 — réplicas e limites
# =====================================================================

def settings(**kw):
    base = dict(lam=1.0, simulation_time=100.0, replications=10, warmup_time=0.0, seed=None, confidence_level=0.95)
    return validate_simulation_settings(**{**base, **kw})


class TestReplicationsAndLimits:
    def test_the_limits_come_from_the_specification(self):
        assert (MIN_REPLICATIONS, MAX_REPLICATIONS, MAX_EVENTS_PER_REPLICATION) == (2, 100, 1_000_000)

    @pytest.mark.parametrize("n", [2, 3, 50, 100])
    def test_accepts_replications_in_range(self, n):
        assert settings(replications=n)[1] == n

    @pytest.mark.parametrize("n", [0, 1, 101, 1000, -5])
    def test_rejects_replications_out_of_range(self, n):
        with pytest.raises(QueueValidationError, match="entre 2 e 100") as exc:
            settings(replications=n)
        assert exc.value.field == "replications"

    @pytest.mark.parametrize("n", [2.5, "10", True, None, 10.0])
    def test_rejects_replications_that_are_not_integers(self, n):
        with pytest.raises(QueueValidationError) as exc:
            settings(replications=n)
        assert exc.value.field == "replications"

    def test_events_per_replication_limit_is_inclusive_at_one_million(self):
        settings(lam=1000.0, simulation_time=1000.0, replications=2)          # exatamente 1.000.000 por réplica
        with pytest.raises(QueueValidationError, match="por réplica") as exc:
            settings(lam=1000.0, simulation_time=1001.0, replications=2)
        assert exc.value.field == "simulation_time"

    def test_total_budget_still_protects_the_server(self):
        # 1.000.000 por réplica é permitido, mas 6 réplicas somam 6.000.000 > 5.000.000
        assert MAX_EXPECTED_ARRIVALS == 5_000_000
        settings(lam=1000.0, simulation_time=1000.0, replications=5)
        with pytest.raises(QueueValidationError, match="no total") as exc:
            settings(lam=1000.0, simulation_time=1000.0, replications=6)
        assert exc.value.field == "simulation_time"

    def test_messages_use_brazilian_thousands_separators(self):
        with pytest.raises(QueueValidationError) as per_rep:
            settings(lam=5000.0, simulation_time=1000.0, replications=2)
        assert "5.000.000 chegadas esperadas por réplica" in str(per_rep.value)
        assert "limite 1.000.000" in str(per_rep.value)
        with pytest.raises(QueueValidationError) as total:
            settings(lam=1000.0, simulation_time=1000.0, replications=6)
        assert "6.000.000 chegadas esperadas no total" in str(total.value)
        assert "limite 5.000.000" in str(total.value)

    def test_the_documentation_example_is_within_the_limits(self):
        settings(lam=40.0, simulation_time=2000.0, replications=10, warmup_time=100.0)

    def test_simulators_apply_the_same_rules(self):
        with pytest.raises(QueueValidationError):
            simulate_mm1(1, 2, 100, replications=1)
        with pytest.raises(QueueValidationError):
            simulate_mmck(1, 1, 2, 5, 100, replications=101)
        with pytest.raises(QueueValidationError):
            simulate_mmck(1000, 2000, 2, None, 5000, replications=2)   # 5.000.000 por réplica


# =====================================================================
# RF-28 — o erro de regra identifica o campo
# =====================================================================

class TestFieldInDomainErrors:
    @pytest.mark.parametrize("call, field", [
        (lambda: validate_mm1_parameters(-1, 50), "lambda"),
        (lambda: validate_mm1_parameters(40, 0), "mu"),
        (lambda: validate_mm1_parameters("40", 50), "lambda"),
        (lambda: validate_mm1_parameters(60, 50), "lambda"),                       # instável
        (lambda: validate_queue_parameters(20, 1, 10, None), "lambda"),            # M/M/c instável
        (lambda: validate_queue_parameters(1, 1, 0, None), "servers"),
        (lambda: validate_queue_parameters(1, 1, 1001, None), "servers"),
        (lambda: validate_queue_parameters(1, 1, 2.5, None), "servers"),
        (lambda: validate_queue_parameters(1, 1, 3, 2), "capacity"),               # K < c
        (lambda: validate_queue_parameters(1, 1, 1, 100_001), "capacity"),
        (lambda: validate_queue_parameters(1, 1, 1, True), "capacity"),
        (lambda: settings(simulation_time=0), "simulation_time"),
        (lambda: settings(warmup_time=-1), "warmup_time"),
        (lambda: settings(warmup_time=100), "warmup_time"),
        (lambda: settings(seed=-1), "seed"),
        (lambda: settings(confidence_level=1.5), "confidence_level"),
        (lambda: settings(replications=1), "replications"),
    ])
    def test_error_carries_the_api_field_name(self, call, field):
        with pytest.raises(QueueValidationError) as exc:
            call()
        assert exc.value.field == field

    def test_instability_and_insufficient_sample_keep_their_types_and_field(self):
        with pytest.raises(UnstableSystemError) as exc:
            validate_mm1_parameters(60, 50)
        assert exc.value.field == "lambda"
        with pytest.raises(InsufficientSampleError) as exc:
            simulate_mm1(1, 2, 0.001, replications=2, seed=1)
        assert exc.value.field == "simulation_time"

    def test_error_without_a_field_is_still_valid(self):
        e = QueueValidationError("mensagem")
        assert e.field is None and str(e) == "mensagem"


@pytest.mark.parametrize("path, payload, code, field", [
    ("/api/models/mm1/calculate", {"lambda": -1, "mu": 50}, "invalid_parameter", "lambda"),
    ("/api/models/mm1/calculate", {"lambda": 60, "mu": 50}, "unstable_system", "lambda"),
    ("/api/models/mm1/simulate", {"lambda": 1, "mu": 2, "simulation_time": 100, "replications": 1}, "invalid_parameter", "replications"),
    ("/api/models/mm1/simulate", {"lambda": 1, "mu": 2, "simulation_time": 100, "replications": 101}, "invalid_parameter", "replications"),
    ("/api/models/mm1/simulate", {"lambda": 1, "mu": 2, "simulation_time": 100, "warmup_time": 100}, "invalid_parameter", "warmup_time"),
    ("/api/models/mm1/simulate", {"lambda": 1, "mu": 2, "simulation_time": 100, "confidence_level": 1.5}, "invalid_parameter", "confidence_level"),
    ("/api/models/mm1/simulate", {"lambda": 1, "mu": 2, "simulation_time": 2_000_000, "replications": 2}, "invalid_parameter", "simulation_time"),
    ("/api/models/mmc/calculate", {"lambda": 20, "mu": 1, "servers": 10}, "unstable_system", "lambda"),
    ("/api/models/mmc/calculate", {"lambda": 1, "mu": 1, "servers": 0}, "invalid_parameter", "servers"),
    ("/api/models/mm1k/calculate", {"lambda": 1, "mu": 1, "capacity": 0}, "invalid_parameter", "capacity"),
    ("/api/models/mmck/compare", {"lambda": 1, "mu": 1, "servers": 3, "capacity": 2, "simulation_time": 100}, "invalid_parameter", "capacity"),
    ("/api/models/mmck/simulate", {"lambda": 1, "mu": 1, "servers": 2, "capacity": 4, "simulation_time": 0.001, "replications": 2, "seed": 1}, "insufficient_sample", "simulation_time"),
])
def test_api_domain_errors_identify_the_field(path, payload, code, field):
    r = client.post(path, json=payload)
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == code
    assert body["fields"] == [{"field": field, "message": body["message"]}]


def test_api_format_errors_still_list_the_fields():
    body = client.post("/api/models/mmc/calculate", json={"mu": 1}).json()
    assert body["code"] == "invalid_request"
    assert {f["field"] for f in body["fields"]} >= {"lambda", "servers"}


# =====================================================================
# P0 pela API
# =====================================================================

MODEL_PAYLOADS = {
    "mm1": {"lambda": 40, "mu": 50},
    "mmc": {"lambda": 8, "mu": 1, "servers": 10},
    "mm1k": {"lambda": 12, "mu": 10, "capacity": 5},
    "mmck": {"lambda": 25, "mu": 10, "servers": 3, "capacity": 6},
}
SIM = {"simulation_time": 150, "replications": 2, "warmup_time": 10, "seed": 3}


@pytest.mark.parametrize("model", MODEL_PAYLOADS)
def test_api_returns_p0_in_every_action(model):
    payload = MODEL_PAYLOADS[model]
    calc = client.post(f"/api/models/{model}/calculate", json=payload).json()
    assert 0 < calc["p0"] <= 1
    sim = client.post(f"/api/models/{model}/simulate", json={**payload, **SIM}).json()
    assert "p0" in sim["summary"] and "p0" in sim["runs"][0]
    cmp_ = client.post(f"/api/models/{model}/compare", json={**payload, **SIM}).json()
    assert cmp_["metrics"]["p0"]["analytical"] == pytest.approx(calc["p0"])
    assert cmp_["metrics"]["p0"]["simulated_mean"] == sim["summary"]["p0"]["mean"]
    assert cmp_["metrics"]["p0"]["ci_low"] <= cmp_["metrics"]["p0"]["ci_high"]


def test_api_mm1_calculate_example_from_the_specification():
    body = client.post("/api/models/mm1/calculate", json={"lambda": 40, "mu": 50}).json()
    assert {k: round(v, 10) for k, v in body.items() if k != "model"} == {
        "rho": 0.8, "L": 4.0, "Lq": 3.2, "W": 0.1, "Wq": 0.08, "p0": 0.2}
