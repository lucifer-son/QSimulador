import pytest

from app.analytical.closed import closed_metrics
from app.domain.validation.errors import QueueValidationError, UnstableSystemError
from app.realdata.compare import (
    Measured,
    SimulationSettings,
    compare_levels,
    compare_with_model,
    derive_think_time,
)
from app.realdata.jmeter import summarize_jmeter
from app.realdata.levels import Level
from tests.helpers_realdata import closed_trace_rows, jmeter_csv


def test_lei_da_resposta_interativa():
    assert derive_think_time(10, 4.0, 0.5) == pytest.approx(2.0)
    with pytest.raises(QueueValidationError) as exc:
        derive_think_time(10, 20.0, 0.5)            # N/X = R: sem tempo de reflexão
    assert exc.value.field == "think_time"


def test_modo_fechado_reproduz_o_modelo_quando_a_medicao_e_o_proprio_modelo():
    m = closed_metrics(10, 1.0, 5.0, 1)
    medido = Measured(m.throughput, m.W * 1000)
    r = compare_with_model(medido, "closed", 5.0, users=10)
    assert r.think_time == pytest.approx(1.0, rel=1e-9) and r.think_time_source == "interactive_law"
    assert r.model == "M/M/1//10"
    for name in ("throughput", "W", "L", "rho"):
        assert r.metrics[name].analytical_error_pct == pytest.approx(0.0, abs=1e-6)
    assert r.metrics["L"].measured_derived and r.metrics["rho"].measured_derived
    assert not r.metrics["W"].measured_derived
    assert r.simulation is None and r.warnings == []


def test_modo_aberto_usa_a_vazao_como_lambda_e_avisa_do_sistema_fechado():
    r = compare_with_model(Measured(40.0, 100.0), "open", 50.0)
    assert r.model == "M/M/1" and r.arrival_rate == 40.0 and r.users is None
    assert r.metrics["W"].analytical == pytest.approx(0.1)           # 1/(μ − λ)
    assert r.metrics["throughput"].role == "input"
    assert r.metrics["throughput"].analytical_error_pct == pytest.approx(0.0, abs=1e-9)
    assert "sistema fechado" in r.warnings[0] and "M/M/c//N" in r.warnings[0]


def test_modo_aberto_instavel_e_rejeitado():
    with pytest.raises(UnstableSystemError) as exc:
        compare_with_model(Measured(60.0, 100.0), "open", 50.0)
    assert exc.value.field == "mu"


def test_avisos_de_mu_e_de_capacidade():
    r = compare_with_model(Measured(40.0, 60.0), "closed", 20.0, "inverse_response", users=10, think_time=0.5)
    texto = " ".join(r.warnings)
    assert "carga baixa" in texto and "excede a capacidade" in texto


def test_erros_de_entrada():
    with pytest.raises(QueueValidationError) as exc:
        compare_with_model(Measured(40.0, 60.0), "closed", 50.0)
    assert exc.value.field == "users"
    with pytest.raises(QueueValidationError) as exc:
        compare_with_model(Measured(40.0, 60.0), "fechado", 50.0)
    assert exc.value.field == "mode"


def test_erro_relativo_usa_o_medido_como_referencia():
    r = compare_with_model(Measured(40.0, 60.0), "closed", 50.0, users=10, think_time=0.19)
    w = r.metrics["W"]
    assert w.analytical_error_pct == pytest.approx(abs(w.analytical - 0.06) / 0.06 * 100)


def test_simulacao_traz_intervalo_e_semente():
    r = compare_with_model(
        Measured(40.0, 60.0), "closed", 50.0, users=10, think_time=0.19,
        simulation=SimulationSettings(1000, 4, 50, seed=3),
    )
    m = r.metrics["W"]
    assert m.ci_low <= m.simulated_mean <= m.ci_high
    assert isinstance(m.measured_within_ci, bool)
    assert r.simulation["seed"] == 3 and r.simulation["replications"] == 4


def test_fechando_o_ciclo_rastro_independente_importado_e_comparado():
    """Gera um teste de carga fechado com código à parte, importa como CSV do JMeter e compara com o modelo."""
    users, think, mu = 10, 1.0, 5.0
    csv = jmeter_csv(closed_trace_rows(users, think, mu, duration=6000, seed=11))
    d = summarize_jmeter("rastro.csv", csv, trim_start_s=200.0, trim_end_s=100.0)
    assert d.users == users
    r = compare_with_model(Measured(d.throughput, d.mean_ms), "closed", mu, users=d.users, think_time=think)
    assert r.metrics["throughput"].analytical_error_pct < 3.0
    assert r.metrics["W"].analytical_error_pct < 5.0
    # na mesma medição, o modelo aberto com λ = X erra bem mais o tempo de resposta
    aberto = compare_with_model(Measured(d.throughput, d.mean_ms), "open", mu)
    assert aberto.metrics["W"].analytical_error_pct > 3 * r.metrics["W"].analytical_error_pct


def test_niveis_calibrados_no_menor_nivel():
    verdade = [(n, closed_metrics(n, 1.0, 5.0, 1)) for n in (1, 5, 10, 20)]
    niveis = [Level(n, m.W * 1000, m.throughput) for n, m in verdade]
    r = compare_levels(niveis)
    assert r.mu == pytest.approx(5.0, rel=1e-9) and r.mu_source == "baseline"
    assert r.think_time == pytest.approx(1.0, rel=1e-9) and r.calibration_users == 1
    assert [lv.users for lv in r.levels] == [1, 5, 10, 20]
    for lv in r.levels:
        assert lv.throughput.analytical_error_pct == pytest.approx(0.0, abs=1e-6)
        assert lv.W.analytical_error_pct == pytest.approx(0.0, abs=1e-6)


def test_niveis_com_mu_e_z_informados_e_aviso_de_calibracao_imprecisa():
    niveis = [Level(8, 100.0, 30.0), Level(16, 200.0, 40.0)]
    r = compare_levels(niveis, mu=50.0, think_time=0.5)
    assert r.mu_source == "informed" and r.think_time_source == "informed" and r.calibration_users is None
    r2 = compare_levels(niveis)           # menor nível com 8 usuários e 1 servidor
    assert any("já pode haver fila" in w for w in r2.warnings)
