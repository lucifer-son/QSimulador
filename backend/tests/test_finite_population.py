"""M/M/c//N: casos de referência, limites e propriedades teóricas."""

import pytest

from app.analytical.finite_population import finite_population_metrics
from app.analytical.mmck import mmc_metrics
from app.domain.models.naming import finite_population_model_name
from app.domain.validation.errors import QueueValidationError


def test_uma_fonte_tem_solucao_fechada():
    # N = 1, c = 1: p0 = 1/(1 + a), X = 1/(Z + 1/μ), W = 1/μ, sem espera.
    mu, z = 4.0, 0.5
    m = finite_population_metrics(mu, 1, 1, z)
    a = (1 / z) / mu
    assert m.p0 == pytest.approx(1 / (1 + a))
    assert m.throughput == pytest.approx(1 / (z + 1 / mu))
    assert m.W == pytest.approx(1 / mu)
    assert m.Wq == pytest.approx(0.0, abs=1e-12)
    assert m.rho == pytest.approx(1 - m.p0)


@pytest.mark.parametrize(
    "mu, c, n, z",
    [(5.0, 1, 20, 1.4), (2.0, 3, 40, 2.0), (10.0, 4, 10, 0.1), (1.0, 2, 200, 100.0)],
)
def test_lei_do_tempo_de_resposta_interativo_e_little(mu, c, n, z):
    m = finite_population_metrics(mu, c, n, z)
    assert m.W == pytest.approx(n / m.throughput - z, rel=1e-9)  # W = N/X − Z
    assert m.L == pytest.approx(m.throughput * m.W, rel=1e-9)    # Little
    assert m.Lq == pytest.approx(m.throughput * m.Wq, rel=1e-9)
    assert m.throughput <= c * mu + 1e-9
    assert 0 <= m.rho <= 1 and m.p_block == 0.0


def test_populacao_grande_aproxima_o_mmc():
    # N → ∞ com N·λ fixo: o sistema se comporta como M/M/c com λ = N/Z.
    lam, mu, c = 8.0, 1.0, 10
    n = 200_000 // 10
    z = n / lam
    finite = finite_population_metrics(mu, c, n, z)
    open_ = mmc_metrics(lam, mu, c)
    assert finite.throughput == pytest.approx(open_.throughput, rel=2e-3)
    assert finite.W == pytest.approx(open_.W, rel=5e-3)


def test_saturacao_vazao_tende_a_c_mu():
    m = finite_population_metrics(2.0, 3, 500, 1.0)
    assert m.throughput == pytest.approx(6.0, rel=1e-3)
    assert m.rho == pytest.approx(1.0, rel=1e-3)


def test_sem_tempo_de_reflexao_todos_ficam_no_sistema():
    m = finite_population_metrics(5.0, 2, 10, 0.0)
    assert m.throughput == 10.0 and m.L == 10.0 and m.W == pytest.approx(1.0)
    assert m.Lq == 8.0 and m.p_wait == 1.0 and m.rho == 1.0
    sem_fila = finite_population_metrics(5.0, 2, 2, 0.0)
    assert sem_fila.Lq == 0.0 and sem_fila.p_wait == 0.0


def test_numericamente_estavel_com_populacao_grande():
    m = finite_population_metrics(1000.0, 1, 50_000, 30.0)
    assert 0 < m.throughput <= 1000.0 + 1e-6


@pytest.mark.parametrize(
    "mu, c, n, z, campo",
    [(0, 1, 5, 1, "mu"), (1, 0, 5, 1, "servers"), (1, 1, 0, 1, "population"),
     (1, 1, 5, -1, "think_time"), (1, 1, 5.5, 1, "population"),
     (1, 1, 5, float("nan"), "think_time"), (1, 1, True, 1, "population")],
)
def test_parametros_invalidos(mu, c, n, z, campo):
    with pytest.raises(QueueValidationError) as erro:
        finite_population_metrics(mu, c, n, z)
    assert erro.value.field == campo


def test_nome_do_modelo():
    assert finite_population_model_name(1, 20) == "M/M/1//20"
    assert finite_population_model_name(4, 50) == "M/M/4//50"
