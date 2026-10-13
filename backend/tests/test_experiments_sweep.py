"""Varredura e comparação de servidores (núcleo, sem passar pela API)."""

import pytest

from app.analytical.mm1 import mm1_metrics
from app.analytical.mmck import mmck_metrics, queue_metrics
from app.domain.validation.errors import InsufficientSampleError, QueueValidationError
from app.experiments import sweep as sweep_module
from app.experiments.sweep import SimulationSettings, run_server_comparison, run_sweep
from app.simulation.mmck import simulate_mmck
from app.simulation.results import MetricSummary


def statuses(result):
    return [p.status for p in result.points]


def field_of(call):
    with pytest.raises(QueueValidationError) as info:
        call()
    return info.value.field


# ---------- a faixa ----------

def test_range_includes_both_ends_and_matches_the_analytical_model():
    result = run_sweep("mm1", "lambda", 10, 45, 5, mu=50)
    assert [p.value for p in result.points] == [10, 15, 20, 25, 30, 35, 40, 45]
    assert result.fixed == {"mu": 50.0}
    last = result.points[-1]
    assert last.metrics == {**mm1_metrics(45, 50).as_dict(), "throughput": 45.0}
    assert last.offered_utilization == pytest.approx(0.9)


def test_range_has_no_floating_point_noise():
    # np.arange(0.1, 0.5 + 0.05, 0.1) acumulava erro (0.30000000000000004); aqui sai exato.
    result = run_sweep("mm1", "lambda", 0.1, 0.5, 0.1, mu=1)
    assert [p.value for p in result.points] == [0.1, 0.2, 0.3, 0.4, 0.5]


def test_range_that_does_not_land_on_the_end_stops_before_it():
    assert [p.value for p in run_sweep("mm1", "lambda", 1, 10, 4, mu=50).points] == [1, 5, 9]


def test_single_point_range():
    assert len(run_sweep("mm1", "lambda", 5, 5, 1, mu=10).points) == 1


@pytest.mark.parametrize("model,variable,fixed", [
    ("mm1", "lambda", {"mu": 10}),
    ("mm1", "mu", {"lam": 0.5}),
    ("mmc", "servers", {"lam": 1, "mu": 2}),
    ("mm1k", "capacity", {"lam": 1, "mu": 2}),
    ("mmck", "lambda", {"mu": 10, "servers": 2, "capacity": 5}),
])
def test_every_model_and_variable_is_calculated(model, variable, fixed):
    result = run_sweep(model, variable, 1, 3, 1, **fixed)
    assert len(result.points) == 3
    assert all(p.status == "ok" and p.message is None for p in result.points)


def test_metric_sets_follow_the_model():
    assert len(run_sweep("mm1", "lambda", 1, 2, 1, mu=5).points[0].metrics) == 7
    assert len(run_sweep("mm1k", "lambda", 1, 2, 1, mu=5, capacity=4).points[0].metrics) == 9


def test_point_matches_the_calculate_endpoint_logic():
    result = run_sweep("mmck", "capacity", 3, 8, 1, lam=25, mu=10, servers=3)
    assert result.points[3].metrics == mmck_metrics(25, 10, 3, 6).as_dict()


# ---------- pontos instáveis (RF-22) ----------

def test_unstable_points_are_flagged_and_stable_ones_are_kept():
    result = run_sweep("mm1", "lambda", 5, 15, 5, mu=10)
    assert statuses(result) == ["ok", "unstable", "unstable"]
    assert result.points[0].metrics is not None
    assert result.points[1].metrics is None and "λ < μ" in result.points[1].message
    # a carga oferecida segue calculada: é ela que mostra onde a saturação começa
    assert result.points[1].offered_utilization == pytest.approx(1.0)


def test_instability_can_be_at_the_low_end_when_sweeping_mu_or_servers():
    assert statuses(run_sweep("mm1", "mu", 5, 15, 5, lam=10)) == ["unstable", "unstable", "ok"]
    assert statuses(run_sweep("mmc", "servers", 1, 5, 1, lam=8, mu=3)) == [
        "unstable", "unstable", "ok", "ok", "ok"
    ]


def test_finite_capacity_never_becomes_unstable():
    result = run_sweep("mm1k", "lambda", 5, 50, 5, mu=10, capacity=5)
    assert set(statuses(result)) == {"ok"}


def test_servers_above_capacity_flag_the_point_instead_of_failing_everything():
    # Com K = 6, c de 7 a 10 não existe. Antes isso derrubava a requisição inteira.
    result = run_sweep("mmck", "servers", 1, 10, 1, lam=25, mu=10, capacity=6)
    assert statuses(result) == ["ok"] * 6 + ["invalid"] * 4
    assert "capacity" in result.points[-1].message


def test_capacity_below_servers_flags_the_point():
    result = run_sweep("mmck", "capacity", 1, 8, 1, lam=25, mu=10, servers=3)
    assert statuses(result) == ["invalid", "invalid"] + ["ok"] * 6
    blocking = [p.metrics["p_block"] for p in result.points[2:]]
    assert blocking == sorted(blocking, reverse=True)   # mais capacidade, menos recusas


# ---------- entradas inválidas ----------

@pytest.mark.parametrize("call,field", [
    (lambda: run_sweep("mm1", "lambda", 1, 5, 0, mu=10), "step"),
    (lambda: run_sweep("mm1", "lambda", 1, 5, -1, mu=10), "step"),
    (lambda: run_sweep("mm1", "lambda", 5, 1, 1, mu=10), "end"),
    (lambda: run_sweep("mm1", "lambda", 0, 5, 1, mu=10), "start"),
    (lambda: run_sweep("mm1", "lambda", -1, 5, 1, mu=10), "start"),
    (lambda: run_sweep("mm1", "lambda", True, 5, 1, mu=10), "start"),
    (lambda: run_sweep("mm1", "lambda", 1, float("nan"), 1, mu=10), "end"),
    (lambda: run_sweep("mm1", "lambda", 1, float("inf"), 1, mu=10), "end"),
    (lambda: run_sweep("mm1", "lambda", 1, 100, 1e-6, mu=10), "step"),       # milhões de pontos
    (lambda: run_sweep("mm1", "lambda", 1, 5, 1), "mu"),                      # falta o μ
    (lambda: run_sweep("mm1", "mu", 1, 5, 1), "lambda"),                      # falta o λ
    (lambda: run_sweep("mm1", "lambda", 1, 5, 1, mu=-3), "mu"),
    (lambda: run_sweep("mmc", "lambda", 1, 5, 1, mu=2), "servers"),
    (lambda: run_sweep("mm1k", "lambda", 1, 5, 1, mu=2), "capacity"),
    (lambda: run_sweep("mmck", "lambda", 1, 5, 1, mu=3, servers=4, capacity=2), "capacity"),
    (lambda: run_sweep("xx", "lambda", 1, 5, 1, mu=1), "model"),
    (lambda: run_sweep("mm1", "foo", 1, 5, 1, mu=1), "variable"),
    (lambda: run_sweep("mm1", "servers", 1, 5, 1, lam=1, mu=2), "variable"),   # o M/M/1 não tem c
    (lambda: run_sweep("mmc", "capacity", 1, 5, 1, lam=1, mu=2, servers=2), "variable"),
    (lambda: run_sweep("mmc", "servers", 1, 5, 1.5, lam=1, mu=2), "step"),    # c é inteiro
    (lambda: run_sweep("mmc", "servers", 0, 5, 1, lam=1, mu=2), "start"),
    (lambda: run_sweep("mmc", "servers", 1, 5000, 1, lam=1, mu=2), "end"),
])
def test_invalid_inputs_name_the_field(call, field):
    assert field_of(call) == field


def test_the_swept_parameter_is_ignored_if_also_sent_as_fixed():
    a = run_sweep("mm1", "lambda", 1, 3, 1, lam=999, mu=10)
    b = run_sweep("mm1", "lambda", 1, 3, 1, mu=10)
    assert a == b


# ---------- simulação opcional ----------

@pytest.fixture
def fake_simulators(monkeypatch):
    """Troca os simuladores por versões instantâneas que registram as chamadas."""
    calls = []

    class Fake:
        def __init__(self, summary):
            self.summary = summary

    def summary(reps):
        return {"W": MetricSummary(mean=1.0, std=0.1, ci_low=0.9, ci_high=1.1, n=reps)}

    def fake_mm1(lam, mu, time, reps, warmup, seed, level):
        calls.append(("mm1", lam, time, reps, seed))
        return Fake(summary(reps))

    def fake_mmck(lam, mu, servers, capacity, time, reps, warmup, seed, level):
        calls.append(("mmck", lam, servers, capacity, time, reps, seed))
        return Fake(summary(reps))

    monkeypatch.setattr(sweep_module, "simulate_mm1", fake_mm1)
    monkeypatch.setattr(sweep_module, "simulate_mmck", fake_mmck)
    return calls


def test_only_stable_points_are_simulated(fake_simulators):
    result = run_sweep("mm1", "lambda", 5, 15, 5, mu=10, simulation=SimulationSettings(100, 3, seed=7))
    assert len(fake_simulators) == 1 and fake_simulators[0][1] == 5.0
    assert result.points[0].simulation is not None
    assert result.points[1].simulation is None and result.points[2].simulation is None


def test_all_points_share_one_seed_and_it_is_reported(fake_simulators):
    result = run_sweep("mmck", "lambda", 2, 6, 2, mu=10, servers=2, capacity=4,
                       simulation=SimulationSettings(100, 3))
    seeds = {call[-1] for call in fake_simulators}
    assert seeds == {result.simulation.seed} and isinstance(result.simulation.seed, int)


def test_without_simulation_nothing_is_simulated(fake_simulators):
    result = run_sweep("mm1", "lambda", 1, 3, 1, mu=10)
    assert fake_simulators == [] and result.simulation is None
    assert all(p.simulation is None for p in result.points)


def test_simulation_budget_is_checked_before_simulating(fake_simulators):
    # 100 pontos x 2.000 s x 10 réplicas x λ ≥ 1 passa de 5.000.000 de chegadas
    call = lambda: run_sweep("mm1", "lambda", 1, 100, 1, mu=1000, simulation=SimulationSettings(2000, 10))
    assert field_of(call) == "simulation_time"
    assert fake_simulators == []


def test_simulation_requires_a_time(fake_simulators):
    call = lambda: run_sweep("mm1", "lambda", 1, 3, 1, mu=10, simulation=SimulationSettings(None))
    assert field_of(call) == "simulation_time"


@pytest.mark.parametrize("settings,field", [
    (SimulationSettings(100, 1), "replications"),
    (SimulationSettings(100, 3, warmup_time=100), "warmup_time"),
    (SimulationSettings(100, 3, confidence_level=1.5), "confidence_level"),
    (SimulationSettings(100, 3, seed=-1), "seed"),
])
def test_simulation_settings_follow_the_single_run_rules(fake_simulators, settings, field):
    assert field_of(lambda: run_sweep("mm1", "lambda", 1, 3, 1, mu=10, simulation=settings)) == field


def test_a_point_with_too_few_customers_keeps_its_analytical_result(monkeypatch):
    def flaky(lam, mu, time, reps, warmup, seed, level):
        if lam < 2:
            raise InsufficientSampleError("curto demais", field="simulation_time")
        return type("R", (), {"summary": {"W": MetricSummary(1.0, 0.1, 0.9, 1.1, reps)}})()

    monkeypatch.setattr(sweep_module, "simulate_mm1", flaky)
    result = run_sweep("mm1", "lambda", 1, 3, 1, mu=10, simulation=SimulationSettings(100, 3, seed=1))
    first = result.points[0]
    assert first.simulation is None and first.message == "curto demais" and first.metrics is not None
    assert result.points[1].simulation is not None


def test_real_simulation_matches_a_direct_run_and_is_reproducible():
    settings = SimulationSettings(simulation_time=300, replications=3, warmup_time=20, seed=5)
    one = run_sweep("mmck", "lambda", 25, 25, 1, mu=10, servers=3, capacity=6, simulation=settings)
    again = run_sweep("mmck", "lambda", 25, 25, 1, mu=10, servers=3, capacity=6, simulation=settings)
    direct = simulate_mmck(25, 10, 3, 6, 300, 3, 20, 5, 0.95)
    assert one.points[0].simulation == direct.summary == again.points[0].simulation
    assert one.simulation.seed == 5


def test_real_simulation_is_close_to_the_analytical_value():
    settings = SimulationSettings(simulation_time=400, replications=3, seed=2)
    result = run_sweep("mm1", "lambda", 4, 6, 2, mu=10, simulation=settings)
    for point in result.points:
        assert point.simulation["rho"].mean == pytest.approx(point.metrics["rho"], abs=0.08)


# ---------- comparação de servidores ----------

def test_server_comparison_orders_series_and_flags_instability_per_series():
    result = run_server_comparison([3, 1, 2], mu=10, start=5, end=25, step=5)
    assert result.model == "mmc" and [s.servers for s in result.series] == [1, 2, 3]
    by_c = {s.servers: [p.status for p in s.points] for s in result.series}
    assert by_c[1] == ["ok"] + ["unstable"] * 4
    assert by_c[2] == ["ok"] * 3 + ["unstable"] * 2
    assert by_c[3] == ["ok"] * 5


def test_more_servers_never_increase_waiting_time():
    result = run_server_comparison([1, 2, 4], mu=10, start=5, end=5, step=1)
    waits = [s.points[0].metrics["Wq"] for s in result.series]
    assert waits == sorted(waits, reverse=True)


def test_series_points_match_the_analytical_model():
    result = run_server_comparison([2, 3], mu=10, start=10, end=10, step=1)
    assert result.series[1].points[0].metrics == queue_metrics(10, 10, 3, None).as_dict()


def test_server_comparison_with_finite_capacity_flags_series_above_capacity():
    result = run_server_comparison([2, 4, 8], mu=10, start=5, end=10, step=5, capacity=6)
    assert result.model == "mmck" and result.capacity == 6
    assert statuses(result.series[2]) == ["invalid", "invalid"]    # c = 8 > K = 6
    assert result.series[1].points[0].status == "ok"


@pytest.mark.parametrize("call,field", [
    (lambda: run_server_comparison([2], mu=10, start=1, end=2, step=1), "servers_list"),
    (lambda: run_server_comparison([2, 2], mu=10, start=1, end=2, step=1), "servers_list"),
    (lambda: run_server_comparison([1] * 9, mu=10, start=1, end=2, step=1), "servers_list"),
    (lambda: run_server_comparison([0, 2], mu=10, start=1, end=2, step=1), "servers"),
    (lambda: run_server_comparison([1, 2], mu=None, start=1, end=2, step=1), "mu"),
    (lambda: run_server_comparison([1, 2], mu=10, start=0, end=2, step=1), "start"),
    (lambda: run_server_comparison([1, 2], mu=10, start=1, end=2, step=0), "step"),
])
def test_server_comparison_invalid_inputs(call, field):
    assert field_of(call) == field
