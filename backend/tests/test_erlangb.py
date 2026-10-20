"""Erlang-B (M/M/c/c): valores de referência, propriedades, dimensionamento e simulação."""

import pytest

from app.analysis.comparison_phase10 import MIN_OBSERVABLE_P0, compare_erlangb
from app.analytical.erlangb import erlangb_metrics, erlangb_size, validate_target_blocking
from app.analytical.mmck import mmck_metrics
from app.domain.models.naming import erlang_b_model_name
from app.domain.validation.errors import QueueValidationError

# Seção 2 de docs/valores-de-referencia.md (μ = 1, então λ = a).
REFERENCE = [
    (2.5, 1, 0.7143), (2.5, 2, 0.4717), (2.5, 3, 0.2822), (2.5, 4, 0.1499), (2.5, 5, 0.0697),
    (2.5, 6, 0.0282), (2.5, 7, 0.0100),
    (10, 10, 0.2146), (10, 14, 0.0568), (10, 18, 0.0071), (10, 22, 0.0004),
    (20, 15, 0.3300), (20, 20, 0.1589), (20, 25, 0.0502), (20, 30, 0.0085),
]


@pytest.mark.parametrize("a, c, expected", REFERENCE)
def test_blocking_matches_the_reference_table(a, c, expected):
    assert erlangb_metrics(a, 1.0, c).p_block == pytest.approx(expected, abs=5e-5)


def test_pabx_icu_and_parking_style_example():
    """M/M/15/15 com 20 Erlangs: um terço das chegadas é perdido."""
    m = erlangb_metrics(lam=20, mu=1, servers=15)
    assert m.p_block == pytest.approx(0.33, abs=5e-5)
    assert m.offered_load == 20 and m.carried_load == pytest.approx(20 * (1 - m.p_block))
    assert m.throughput == pytest.approx(13.4, abs=1e-3) and m.lost_rate == pytest.approx(20 * m.p_block)
    assert m.rho == pytest.approx(m.carried_load / 15)
    assert (m.Lq, m.Wq, m.p_wait) == (0.0, 0.0, 0.0)
    assert erlang_b_model_name(15) == "M/M/15/15"


def test_rates_are_rescaled_by_the_offered_load_only():
    """Só a = λ/μ importa para o bloqueio; W = 1/μ."""
    slow = erlangb_metrics(2.0, 0.1, 25)
    fast = erlangb_metrics(200.0, 10.0, 25)
    assert slow.p_block == pytest.approx(fast.p_block)
    assert slow.W == pytest.approx(10.0) and fast.W == pytest.approx(0.1)


# ---------- propriedades ----------

def test_blocking_decreases_with_servers_and_increases_with_load():
    by_c = [erlangb_metrics(8.0, 1.0, c).p_block for c in range(1, 40)]
    assert all(x > y for x, y in zip(by_c, by_c[1:]))
    by_a = [erlangb_metrics(a, 1.0, 10).p_block for a in (0.5, 1, 2, 5, 10, 20, 50)]
    assert all(x < y for x, y in zip(by_a, by_a[1:]))


@pytest.mark.parametrize("lam, mu, c", [(0.3, 1, 1), (2.5, 1, 3), (20, 1, 15), (120, 4, 40), (900, 1, 1000), (5, 0.5, 8)])
def test_mmck_with_k_equal_c_coincides_with_erlang_b(lam, mu, c):
    b, k = erlangb_metrics(lam, mu, c), mmck_metrics(lam, mu, c, c)
    for name in ("rho", "L", "Lq", "W", "Wq", "p0", "throughput", "p_wait", "p_block"):
        assert getattr(b, name) == pytest.approx(getattr(k, name), rel=1e-9, abs=1e-300), name


@pytest.mark.parametrize("lam, mu, c", [(2.5, 1, 3), (20, 1, 15), (300, 1, 250)])
def test_littles_law_and_flow_balance(lam, mu, c):
    m = erlangb_metrics(lam, mu, c)
    assert m.L == pytest.approx(m.throughput * m.W)                 # Lei de Little
    assert m.throughput + m.lost_rate == pytest.approx(lam)         # o que chega ou entra ou se perde
    assert 0 < m.rho < 1 and 0 < m.p0 < 1


def test_numerically_stable_for_large_systems():
    m = erlangb_metrics(lam=9000, mu=10, servers=1000)              # a = 900
    assert 1e-6 < m.p_block < 1e-3 and m.rho == pytest.approx(0.9, rel=1e-3)
    assert m.p0 == 0.0 or m.p0 < 1e-300                             # P₀ some, mas o cálculo não estoura
    assert m.L == pytest.approx(m.throughput * m.W)
    assert erlangb_metrics(1e6, 1.0, 1000).p_block == pytest.approx(1 - 1000 / 1e6, rel=1e-3)


# ---------- dimensionamento ----------

def test_size_finds_the_smallest_c_for_the_target():
    s = erlangb_size(20, 1, 0.01)
    assert s.servers == 30 and s.blocking <= 0.01 < s.blocking_previous
    assert s.blocking == pytest.approx(erlangb_metrics(20, 1, 30).p_block)
    assert s.blocking_previous == pytest.approx(erlangb_metrics(20, 1, 29).p_block)


@pytest.mark.parametrize("a, target, expected_c", [(2.5, 0.0101, 7), (10, 0.0569, 14), (10, 0.0072, 18), (20, 0.0503, 25)])
def test_size_against_reference_table(a, target, expected_c):
    assert erlangb_size(a, 1, target).servers == expected_c


def test_size_edge_cases():
    one = erlangb_size(0.01, 1, 0.5)
    assert one.servers == 1 and one.blocking_previous is None
    assert erlangb_size(20, 1, 0.9999).servers == 1
    with pytest.raises(QueueValidationError) as error:
        erlangb_size(5000, 1, 0.01)                                 # nem 1000 servidores bastam
    assert error.value.field == "target_blocking"


@pytest.mark.parametrize("target", [0, -0.1, 1, 1.5, float("nan"), float("inf"), True, "0.1", None])
def test_target_blocking_must_be_a_probability(target):
    with pytest.raises(QueueValidationError) as error:
        validate_target_blocking(target)
    assert error.value.field == "target_blocking" or "target_blocking" in str(error.value)


def test_size_is_minimal_for_many_loads():
    for a in (0.5, 3, 11, 47, 130):
        for target in (0.2, 0.05, 0.01, 0.001):
            s = erlangb_size(a, 1, target)
            assert erlangb_metrics(a, 1, s.servers).p_block <= target
            if s.servers > 1:
                assert erlangb_metrics(a, 1, s.servers - 1).p_block > target


# ---------- validação ----------

@pytest.mark.parametrize("lam, mu, servers, field", [
    (0, 1, 3, "λ"), (-1, 1, 3, "λ"), (1, 0, 3, "μ"), (1, float("inf"), 3, "μ"),
    (1, 1, 0, "servers"), (1, 1, 1.5, "servers"), (1, 1, True, "servers"), (1, 1, 1001, "servers"),
])
def test_invalid_parameters(lam, mu, servers, field):
    with pytest.raises(QueueValidationError) as error:
        erlangb_metrics(lam, mu, servers)
    assert field in (error.value.field or "") or field in str(error.value)


def test_erlang_b_has_no_stability_condition():
    assert erlangb_metrics(1000, 1, 2).p_block > 0.99                # tráfego muito acima da capacidade


# ---------- simulação ----------

@pytest.mark.parametrize("lam, mu, c, seed", [(2.5, 1, 3, 11), (20, 1, 15, 12), (8, 1, 10, 13), (30, 2, 12, 14)])
def test_simulation_agrees_with_erlang_b(lam, mu, c, seed):
    result = compare_erlangb(lam, mu, c, simulation_time=1500, replications=10, warmup_time=100, seed=seed)
    assert result.all_within_ci is True
    assert result.metrics["p_block"].relative_error_pct < 5
    assert result.metrics["rho"].relative_error_pct < 2


def test_comparison_omits_p0_when_it_cannot_be_observed():
    tiny = compare_erlangb(20, 1, 15, simulation_time=500, replications=4, seed=1)
    assert "p0" not in tiny.metrics and erlangb_metrics(20, 1, 15).p0 < MIN_OBSERVABLE_P0
    visible = compare_erlangb(2.5, 1, 3, simulation_time=500, replications=4, seed=1)
    assert "p0" in visible.metrics and len(visible.metrics) == 9
