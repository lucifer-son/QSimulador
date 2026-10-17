import pytest

from app.analytical.mg1 import mg1_metrics
from app.analytical.mm1 import mm1_metrics
from app.domain.service.distributions import build_distribution
from app.domain.validation.errors import QueueValidationError, UnstableSystemError

# Valores de referência: docs/valores-de-referencia.md, seções 4 e 5 (λ e μ por hora).


def dist(key, **params):
    return build_distribution(key, params)


# ---------- valores exatos ----------

def test_md1_lambda_40_mu_80():
    m = mg1_metrics(40, dist("deterministic", mu=80))
    assert m.rho == pytest.approx(0.5)
    assert m.Wq * 3600 == pytest.approx(22.5)            # M/M/1 equivalente: 45 s
    assert mm1_metrics(40, 80).Wq * 3600 == pytest.approx(45.0)


def test_md1_lambda_15_mu_20():
    m = mg1_metrics(15, dist("deterministic", mu=20))
    assert m.Wq * 60 == pytest.approx(4.5)               # M/M/1 equivalente: 9 min
    assert mm1_metrics(15, 20).Wq * 60 == pytest.approx(9.0)


def test_mg1_lambda_25_mu_30_cv_05():
    m = mg1_metrics(25, dist("lognormal", mu=30, cv=0.5))
    assert m.Lq == pytest.approx(2.6042, abs=5e-5)
    assert m.Wq * 60 == pytest.approx(6.25, abs=1e-6)
    assert m.Lq / mm1_metrics(25, 30).Lq == pytest.approx(0.625)   # (1 + CV²)/2


# ---------- propriedades ----------

CASES = [
    ("deterministic", {"mean": 0.5}), ("exponential", {"mean": 0.5}), ("erlang", {"mean": 0.5, "k": 3}),
    ("lognormal", {"mean": 0.5, "cv": 1.7}), ("weibull", {"mean": 0.5, "cv": 0.6}),
    ("uniform", {"min": 0.1, "max": 0.9}), ("triangular", {"min": 0.1, "mode": 0.2, "max": 0.9}),
    ("truncated_normal", {"loc": 0.5, "scale": 0.3}),
]


def test_cv_1_reproduz_o_mm1():
    for key, params in (("exponential", {"mean": 1 / 50}), ("lognormal", {"mean": 1 / 50, "cv": 1.0}),
                        ("weibull", {"mean": 1 / 50, "cv": 1.0})):
        a, b = mg1_metrics(40, build_distribution(key, params)), mm1_metrics(40, 50)
        for name in ("rho", "L", "Lq", "W", "Wq", "p0"):
            assert getattr(a, name) == pytest.approx(getattr(b, name), rel=1e-6)


def test_cv_0_reproduz_o_md1_e_metade_do_mm1():
    m = mg1_metrics(40, dist("deterministic", mean=1 / 50))
    assert m.Lq == pytest.approx(mm1_metrics(40, 50).Lq / 2)
    # M/D/1: Lq = ρ²/(2(1 − ρ))
    assert m.Lq == pytest.approx(0.8**2 / (2 * 0.2))


@pytest.mark.parametrize("key,params", CASES)
def test_lei_de_little_e_identidades(key, params):
    d = build_distribution(key, params)
    m = mg1_metrics(1.0, d)
    assert m.L == pytest.approx(1.0 * m.W)
    assert m.Lq == pytest.approx(1.0 * m.Wq)
    assert m.W == pytest.approx(m.Wq + d.mean)
    assert m.L == pytest.approx(m.Lq + m.rho)
    assert m.p0 == pytest.approx(1 - m.rho)
    # Pollaczek-Khinchine na forma com CV
    assert m.Lq == pytest.approx(m.rho**2 * (1 + d.cv**2) / (2 * (1 - m.rho)))


def test_espera_cresce_com_a_variabilidade():
    wq = [mg1_metrics(1.0, dist("lognormal", mean=0.5, cv=cv)).Wq for cv in (0.1, 0.5, 1.0, 2.0)]
    assert wq == sorted(wq)


# ---------- estabilidade e validação ----------

@pytest.mark.parametrize("lam", [2.0, 3.0])
def test_instavel_quando_rho_maior_ou_igual_a_1(lam):
    with pytest.raises(UnstableSystemError) as exc:
        mg1_metrics(lam, dist("deterministic", mean=0.5))
    assert exc.value.field == "lambda" and "M/G/1" in str(exc.value)


@pytest.mark.parametrize("lam", [0, -1, float("nan"), float("inf"), True, "1"])
def test_lambda_invalido(lam):
    with pytest.raises(QueueValidationError) as exc:
        mg1_metrics(lam, dist("deterministic", mean=0.5))
    assert exc.value.field == "lambda"
