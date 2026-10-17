import math

import numpy as np
import pytest
from scipy import stats

from app.domain.service.distributions import (
    CATALOG, DISTRIBUTION_KEYS, build_distribution,
)
from app.domain.validation.errors import QueueValidationError

# Um exemplo válido de cada distribuição.
CASES = {
    "deterministic": {"mean": 0.02},
    "exponential": {"mean": 0.02},
    "erlang": {"mean": 0.02, "k": 4},
    "lognormal": {"mean": 0.02, "cv": 0.8},
    "weibull": {"mean": 0.02, "cv": 0.8},
    "uniform": {"min": 0.01, "max": 0.03},
    "triangular": {"min": 0.01, "mode": 0.015, "max": 0.04},
    "truncated_normal": {"loc": 0.02, "scale": 0.02},
}

# Tolerâncias relativas (amostra de 200 mil) calibradas pela variação entre 8 sementes:
# ~2x o pior erro observado (média: 0,43%; variância: 1,4%).
MEAN_TOL, VAR_TOL = 0.01, 0.03


def test_catalogo_cobre_as_oito_distribuicoes_na_ordem():
    assert DISTRIBUTION_KEYS == tuple(CASES)
    assert tuple(spec.key for spec in CATALOG) == DISTRIBUTION_KEYS
    for spec in CATALOG:
        built = build_distribution(spec.key, spec.example)   # o exemplo do catálogo é válido
        assert built.mean > 0


# ---------- momentos teóricos ----------

def test_momentos_exatos():
    assert build_distribution("deterministic", {"mean": 2}).variance == 0
    e = build_distribution("exponential", {"mean": 2})
    assert (e.mean, e.variance, e.cv) == (2, 4, 1)
    k4 = build_distribution("erlang", {"mean": 2, "k": 4})
    assert k4.variance == pytest.approx(1.0) and k4.cv == pytest.approx(0.5)
    u = build_distribution("uniform", {"min": 1, "max": 3})
    assert u.mean == 2 and u.variance == pytest.approx(4 / 12)
    t = build_distribution("triangular", {"min": 0, "mode": 3, "max": 6})
    assert t.mean == pytest.approx(3) and t.variance == pytest.approx((0 + 36 + 9 - 0 - 0 - 18) / 18)


@pytest.mark.parametrize("key", ["lognormal", "weibull"])
@pytest.mark.parametrize("cv", [0.1, 0.5, 1.0, 2.5])
def test_cv_pedido_e_o_cv_obtido(key, cv):
    d = build_distribution(key, {"mean": 3.0, "cv": cv})
    assert d.mean == 3.0 and d.cv == pytest.approx(cv, rel=1e-9)


def test_weibull_com_cv_1_e_exponencial():
    w = build_distribution("weibull", {"mean": 1.0, "cv": 1.0})
    assert w.parameters["shape"] == pytest.approx(1.0, abs=1e-6)


def test_normal_truncada_usa_os_momentos_da_truncada():
    d = build_distribution("truncated_normal", {"loc": 0.0, "scale": 1.0})
    # Meia-normal: média √(2/π) e variância 1 − 2/π (não 0 e 1 da normal original).
    assert d.mean == pytest.approx(math.sqrt(2 / math.pi))
    assert d.variance == pytest.approx(1 - 2 / math.pi)
    ref = stats.truncnorm(0, np.inf, loc=0.0, scale=1.0)
    assert d.mean == pytest.approx(ref.mean()) and d.variance == pytest.approx(ref.var())


def test_normal_truncada_com_loc_alto_se_aproxima_da_normal():
    d = build_distribution("truncated_normal", {"loc": 10.0, "scale": 1.0})
    assert d.mean == pytest.approx(10.0, rel=1e-6) and d.variance == pytest.approx(1.0, rel=1e-6)


def test_mu_equivale_a_media():
    a = build_distribution("exponential", {"mu": 50})
    b = build_distribution("exponential", {"mean": 0.02})
    assert a.mean == pytest.approx(b.mean) and a.mu == pytest.approx(50)


# ---------- amostras ----------

@pytest.mark.parametrize("key", list(CASES))
def test_media_e_variancia_da_amostra(key):
    d = build_distribution(key, CASES[key])
    x = d.sample(np.random.default_rng(0), 200_000)
    assert x.min() >= 0
    assert x.mean() == pytest.approx(d.mean, rel=MEAN_TOL)
    if d.variance == 0:
        assert x.var() == pytest.approx(0, abs=1e-20)
    else:
        assert x.var() == pytest.approx(d.variance, rel=VAR_TOL)


@pytest.mark.parametrize("key", list(CASES))
def test_amostrador_e_reprodutivel_pela_semente(key):
    d = build_distribution(key, CASES[key])
    a, b = d.sampler(np.random.default_rng(7)), d.sampler(np.random.default_rng(7))
    assert [a() for _ in range(5000)] == [b() for _ in range(5000)]   # atravessa mais de um bloco


def test_amostrador_entrega_floats_positivos():
    for key, params in CASES.items():
        value = build_distribution(key, params).sampler(np.random.default_rng(1))()
        assert isinstance(value, float) and value >= 0


# ---------- validação ----------

def err(key, values):
    with pytest.raises(QueueValidationError) as exc:
        build_distribution(key, values)
    return exc.value


@pytest.mark.parametrize("key", ["deterministic", "exponential", "erlang", "lognormal", "weibull"])
def test_exige_media_ou_mu(key):
    extra = {"k": 2, "cv": 1.0}
    e = err(key, extra)
    assert e.field == "mean"


def test_media_e_mu_juntos_sao_rejeitados():
    assert err("exponential", {"mean": 1, "mu": 1}).field == "mean"


@pytest.mark.parametrize("values,field", [
    ({"mean": 0}, "mean"), ({"mean": -1}, "mean"), ({"mu": 0}, "mu"), ({"mean": float("inf")}, "mean"),
    ({"mean": float("nan")}, "mean"),
])
def test_media_invalida(values, field):
    assert err("exponential", values).field == field


@pytest.mark.parametrize("k", [0, -2, 1001, 2.5, True, "3"])
def test_erlang_exige_k_inteiro_de_1_a_1000(k):
    assert err("erlang", {"mean": 1, "k": k}).field == "k"


def test_erlang_exige_k():
    assert err("erlang", {"mean": 1}).field == "k"


@pytest.mark.parametrize("key", ["lognormal", "weibull"])
@pytest.mark.parametrize("cv", [0, -1, 0.001, 10.5])
def test_cv_fora_da_faixa(key, cv):
    assert err(key, {"mean": 1, "cv": cv}).field == "cv"


@pytest.mark.parametrize("values,field", [
    ({"min": 2, "max": 2}, "max"), ({"min": 3, "max": 2}, "max"), ({"min": -1, "max": 2}, "min"),
    ({"min": 1}, "max"), ({"max": 2}, "min"),
])
def test_uniforme_invalida(values, field):
    assert err("uniform", values).field == field


@pytest.mark.parametrize("values,field", [
    ({"min": 1, "mode": 0.5, "max": 3}, "mode"), ({"min": 1, "mode": 3.5, "max": 3}, "mode"),
    ({"min": 3, "mode": 3, "max": 3}, "max"), ({"min": 1, "max": 3}, "mode"),
])
def test_triangular_invalida(values, field):
    assert err("triangular", values).field == field


def test_triangular_aceita_moda_nas_pontas():
    assert build_distribution("triangular", {"min": 1, "mode": 1, "max": 3}).mean == pytest.approx(5 / 3)
    assert build_distribution("triangular", {"min": 1, "mode": 3, "max": 3}).mean == pytest.approx(7 / 3)


@pytest.mark.parametrize("values,field", [
    ({"loc": 1, "scale": 0}, "scale"), ({"loc": 1, "scale": -1}, "scale"), ({"scale": 1}, "loc"),
    ({"loc": -11, "scale": 1}, "loc"),
])
def test_normal_truncada_invalida(values, field):
    assert err("truncated_normal", values).field == field


def test_distribuicao_desconhecida():
    assert err("gama", {"mean": 1}).field == "distribution"
