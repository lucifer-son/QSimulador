"""Comparação tripla: medido × analítico × simulação."""

import pytest

from app.analytical.finite_population import finite_population_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.realdata.levels import parse_levels
from app.realdata.recommendation import compare_chosen
from app.realdata.simulated import SimulationSettings, compare_simulated

MU, Z = 5.0, 1.0


def levels_from_model(users=(1, 5, 10, 20)):
    """Um arquivo agregado cujos valores são exatamente os do modelo M/M/1//N."""
    rows = []
    for n in users:
        m = finite_population_metrics(MU, 1, n, Z)
        rows.append(f"{n},{m.W * 1000},,{m.throughput},0")
    return parse_levels("n.csv", "users,avg_ms,p90_ms,throughput,error_rate\n" + "\n".join(rows) + "\n").levels


SIM = SimulationSettings(simulation_time=1500, replications=6, warmup_time=100, seed=11)


def test_acrescenta_a_simulacao_sem_alterar_a_comparacao_existente():
    levels = levels_from_model()
    notation, base = compare_chosen("mm1n", levels, MU, think_time=Z)
    notation2, triple, used = compare_simulated("mm1n", levels, MU, SIM, think_time=Z)
    assert notation2 == notation == "M/M/1//N"
    for a, b in zip(base, triple):
        assert a["users"] == b["users"]
        for name, metric in a["metrics"].items():
            for key, value in metric.items():
                assert b["metrics"][name][key] == value          # os campos de antes não mudam
    assert used == {"simulation_time": 1500, "replications": 6, "warmup_time": 100, "seed": 11, "confidence_level": 0.95}


def test_simulacao_concorda_com_o_modelo_e_com_o_medido():
    levels = levels_from_model()
    _, comparison, _ = compare_simulated("mm1n", levels, MU, SIM, think_time=Z)
    for row in comparison:
        for name in ("W", "throughput"):
            m = row["metrics"][name]
            assert m["relative_error_pct"] == pytest.approx(0.0, abs=1e-6)       # medido = modelo
            assert m["simulated_error_pct"] < 6.0
            assert m["simulated_ci_low"] <= m["simulated_mean"] <= m["simulated_ci_high"]
            assert m["simulation_within_observed_ci"] is None                    # arquivo agregado: sem IC do medido
        assert "L" in row["metrics"] and row["metrics"]["L"]["simulated_mean"] is not None


def test_semente_do_nivel_i_e_semente_base_mais_i_e_e_reprodutivel():
    levels = levels_from_model((2, 6))
    a = compare_simulated("mm1n", levels, MU, SIM, think_time=Z)
    b = compare_simulated("mm1n", levels, MU, SIM, think_time=Z)
    assert a == b
    c = compare_simulated("mm1n", levels, MU, SimulationSettings(1500, 6, 100, 12), think_time=Z)
    assert a[1][0]["metrics"]["W"]["simulated_mean"] != c[1][0]["metrics"]["W"]["simulated_mean"]


def test_semente_omitida_e_sorteada_e_devolvida():
    _, _, used = compare_simulated("mm1n", levels_from_model((2,)), MU, SimulationSettings(300, 3), think_time=Z)
    assert isinstance(used["seed"], int)


def test_modelo_aberto_simula_com_lambda_do_nivel():
    levels = parse_levels("n.csv", "users,avg_ms,throughput\n1,125,4\n").levels      # λ̂ = 4, μ = 8
    _, comparison, _ = compare_simulated("mm1", levels, 8.0, SimulationSettings(2000, 5, 100, 3))
    w = comparison[0]["metrics"]["W"]
    assert w["model"] == pytest.approx(1 / (8 - 4))
    assert abs(w["simulated_mean"] - w["model"]) / w["model"] < 0.1


def test_modelo_aberto_com_capacidade_traz_bloqueio_simulado():
    levels = parse_levels("n.csv", "users,avg_ms,throughput\n1,300,6\n").levels
    _, comparison, _ = compare_simulated("mm1k", levels, 5.0, SimulationSettings(2000, 5, 100, 3), capacity=4)
    assert "p_block" in comparison[0]["metrics"]
    assert comparison[0]["metrics"]["p_block"]["simulated_mean"] > 0


def test_erros_da_comparacao_e_da_simulacao_sao_propagados():
    levels = levels_from_model((2,))
    with pytest.raises(QueueValidationError) as exc:
        compare_simulated("mm1n", levels, MU, SIM)                                # falta think_time
    assert exc.value.field == "think_time"
    with pytest.raises(QueueValidationError) as exc:
        compare_simulated("mm1n", levels, MU, SimulationSettings(1500, 1), think_time=Z)
    assert exc.value.field == "replications"
    with pytest.raises(UnstableSystemError):
        compare_simulated("mm1", parse_levels("n.csv", "users,avg_ms,throughput\n1,100,10\n").levels, 8.0, SIM)
