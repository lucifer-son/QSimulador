"""Ajuste de distribuição (Fase 13, RFC-25 e RFC-26; decisão D-02)."""

import math

import numpy as np
import pytest
from scipy import stats

from app.analysis import fit as fit_module
from app.analysis.fit import (
    CANDIDATE_KEYS, FAMILIES, MAX_FIT_WORK, MAX_SAMPLE_VALUES, _stats, bootstrap_p_value, fit_sample,
    iter_fit, ks_distance, validate_bootstrap,
)
from app.domain.service.distributions import build_distribution
from app.domain.validation.errors import QueueValidationError
from app.domain.validation.realdata import MAX_UPLOAD_BYTES

TRUE = {
    "exponential": {"mean": 2.0},
    "erlang": {"k": 4, "rate": 2.0, "mean": 2.0},
    "lognormal": {"mu": 0.5, "sigma": 0.6},
    "weibull": {"shape": 1.8, "scale": 3.0},
    "uniform": {"min": 1.0, "max": 3.0},
}


def draw(key, n, seed):
    return FAMILIES[key].sample(np.random.default_rng(seed), n, TRUE[key])


def by_key(result):
    return {c["key"]: c for c in result["candidates"]}


# ---------- verossimilhança exata onde há fórmula ----------

def test_exponential_loglik_and_aic_are_exact():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    r = fit_sample(x.tolist(), bootstrap=0, seed=1)
    c = by_key(r)["exponential"]
    assert c["parameters"]["mean"] == pytest.approx(5.5)
    assert c["loglik"] == pytest.approx(-10 * math.log(5.5) - 10)
    assert c["aic"] == pytest.approx(2 + 2 * (10 * math.log(5.5) + 10))


def test_uniform_loglik_is_minus_n_log_range_and_aic_is_flagged_not_comparable():
    x = np.linspace(1, 3, 20)
    c = by_key(fit_sample(x.tolist(), bootstrap=0, seed=1))["uniform"]
    assert (c["parameters"]["min"], c["parameters"]["max"]) == (1.0, 3.0)
    assert c["loglik"] == pytest.approx(-20 * math.log(2.0))
    assert c["comparable_aic"] is False and c["delta_aic"] is None and c["akaike_weight"] is None
    assert any("não é comparável" in note for note in c["notes"])


def test_erlang_with_k_one_equals_the_exponential():
    x = draw("exponential", 500, 3)
    r = fit_sample(x.tolist(), bootstrap=0, seed=1)
    c = by_key(r)
    if c["erlang"]["parameters"]["k"] == 1:
        assert c["erlang"]["loglik"] == pytest.approx(c["exponential"]["loglik"])
        assert any("k = 1" in n for n in c["erlang"]["notes"])


def test_lognormal_matches_scipy_mle():
    x = draw("lognormal", 800, 4)
    c = by_key(fit_sample(x.tolist(), bootstrap=0, seed=1))["lognormal"]
    shape, loc, scale = stats.lognorm.fit(x, floc=0)
    assert c["parameters"]["sigma"] == pytest.approx(shape, rel=1e-6)
    assert c["parameters"]["mu"] == pytest.approx(math.log(scale), rel=1e-6)
    assert c["loglik"] == pytest.approx(stats.lognorm.logpdf(x, shape, 0, scale).sum(), rel=1e-9)


def test_weibull_matches_scipy_mle():
    x = draw("weibull", 800, 5)
    c = by_key(fit_sample(x.tolist(), bootstrap=0, seed=1))["weibull"]
    shape, loc, scale = stats.weibull_min.fit(x, floc=0)
    assert c["parameters"]["shape"] == pytest.approx(shape, rel=1e-4)
    assert c["parameters"]["scale"] == pytest.approx(scale, rel=1e-4)
    assert c["loglik"] == pytest.approx(stats.weibull_min.logpdf(x, shape, 0, scale).sum(), rel=1e-6)


# ---------- recuperação dos parâmetros (tolerância calibrada entre 30 sementes, n = 2000) ----------
# Erro relativo máximo medido: exponencial 0,049; Erlang (média) 0,029 e k exato; lognormal μ 0,081 e σ 0,042;
# Weibull 0,044 e 0,028; uniforme 0,004. Tolerância ≈ 1,7 a 2× o pior.

@pytest.mark.parametrize("key,checks", [
    ("exponential", {"mean": 0.09}),
    ("erlang", {"mean": 0.05}),
    ("lognormal", {"mu": 0.15, "sigma": 0.08}),
    ("weibull", {"shape": 0.08, "scale": 0.05}),
    ("uniform", {"min": 0.01, "max": 0.01}),
])
@pytest.mark.parametrize("seed", [101, 102, 103])
def test_parameters_are_recovered(key, checks, seed):
    c = by_key(fit_sample(draw(key, 2000, seed).tolist(), bootstrap=0, seed=1))[key]
    for name, tol in checks.items():
        assert c["parameters"][name] == pytest.approx(TRUE[key][name], rel=tol), name
    if key == "erlang":
        assert c["parameters"]["k"] == 4


@pytest.mark.parametrize("key", ["erlang", "lognormal", "weibull", "uniform"])
def test_best_aic_and_adequacy_point_to_the_true_family(key):
    r = fit_sample(draw(key, 1000, 7).tolist(), bootstrap=200, seed=2)
    if key != "uniform":                         # o AIC da uniforme não entra na escolha
        assert r["best"] == key
    c = by_key(r)
    assert c[key]["adequate"] is True
    assert c["exponential"]["adequate"] is False
    assert key in r["adequate"] and r["none_adequate"] is False


def test_exponential_sample_has_cv_near_one_and_suggests_mmc():
    r = fit_sample(draw("exponential", 2000, 8).tolist(), bootstrap=200, seed=2)
    assert r["cv"] == pytest.approx(1.0, abs=0.1)
    assert r["cv_ci"][0] < 1.0 < r["cv_ci"][1]
    assert r["suggestion"]["model"] == "M/M/c"
    assert r["service_suggestion"] == {"distribution": "exponential", "mean": pytest.approx(r["mean"])}
    assert by_key(r)["exponential"]["adequate"] is True


def test_constant_sample_is_degenerate_and_suggests_mdc():
    r = fit_sample([2.5] * 50, bootstrap=200, seed=1)
    assert r["degenerate"] is True and r["cv"] == 0.0 and r["candidates"] == []
    assert r["suggestion"]["model"] == "M/D/c"
    assert r["service_suggestion"] == {"distribution": "deterministic", "mean": 2.5}
    assert "constante" in r["warnings"][0]


def test_non_exponential_sample_suggests_mgc_with_a_service_the_lab_accepts():
    r = fit_sample(draw("lognormal", 1000, 9).tolist(), bootstrap=200, seed=2)
    assert r["suggestion"]["model"] == "M/G/c"
    spec = dict(r["service_suggestion"])
    service = build_distribution(spec.pop("distribution"), spec)       # o M/G/c consegue usar
    assert spec and service.mean == pytest.approx(r["mean"], rel=0.05)
    assert r["service_suggestion"]["distribution"] == "lognormal"


def test_interarrival_kind_has_no_service_suggestion():
    r = fit_sample(draw("exponential", 500, 1).tolist(), kind="interarrival", bootstrap=0, seed=1)
    assert r["service_suggestion"] is None and r["suggestion"]["kind"] == "interarrival"


# ---------- "nenhuma candidata é adequada" ----------

def test_bimodal_sample_has_no_adequate_candidate_and_says_so():
    rng = np.random.default_rng(5)
    x = np.concatenate([rng.normal(1.0, 0.05, 500), rng.normal(5.0, 0.2, 500)])
    r = fit_sample(x.tolist(), bootstrap=200, seed=1)
    assert r["none_adequate"] is True and r["adequate"] == []
    assert any("Nenhuma candidata é adequada" in w for w in r["warnings"])
    assert all(c["p_value"] <= 0.05 for c in r["candidates"])


def test_without_bootstrap_there_is_no_adequacy_claim():
    r = fit_sample(draw("weibull", 300, 2).tolist(), bootstrap=0, seed=1)
    assert r["none_adequate"] is None and r["adequate"] == []
    assert all(c["p_value"] is None and c["adequate"] is None for c in r["candidates"])
    assert any("Sem p-valor" in w for w in r["warnings"])


# ---------- p-valor ----------

def test_p_value_formula_and_monte_carlo_error():
    r = fit_sample(draw("lognormal", 200, 1).tolist(), bootstrap=200, seed=3)
    for c in r["candidates"]:
        assert 1 / 201 <= c["p_value"] <= 1
        assert (c["p_value"] * 201) == pytest.approx(round(c["p_value"] * 201))        # (1 + k)/(B + 1)
        assert c["p_value_se"] == pytest.approx(math.sqrt(c["p_value"] * (1 - c["p_value"]) / 200))


def test_same_seed_same_result_and_seed_is_reported():
    x = draw("weibull", 300, 6).tolist()
    assert fit_sample(x, bootstrap=40, seed=5) == fit_sample(x, bootstrap=40, seed=5)
    assert fit_sample(x, bootstrap=0)["seed"] >= 0


def test_bootstrap_p_value_is_uniform_while_the_plain_ks_is_inflated():
    # Sob H0 o p-valor deve ter média 0,5. Medido em 60 amostras (n = 100, B = 200): Monte Carlo 0,493 e
    # KS simples com parâmetros estimados 0,685 (infla o p-valor: aceita demais). É a razão de ser da D-02.
    fam = FAMILIES["exponential"]
    mc, naive = [], []
    for r in range(60):
        x = np.sort(fam.sample(np.random.default_rng([5, r]), 100, {"mean": 2.0}))
        params = fam.fit(x, _stats(x))
        d = ks_distance(fam.cdf(x, params))
        mc.append(bootstrap_p_value(fam, x, params, d, 200, np.random.default_rng([1, r])))
        naive.append(stats.kstwobign.sf(d * math.sqrt(100)))
    assert 0.39 <= np.mean(mc) <= 0.61                  # ± 3 erros-padrão (0,29/√60 ≈ 0,037)
    assert np.mean(naive) - np.mean(mc) > 0.1


def test_ks_distance_known_value():
    assert ks_distance(np.array([0.5])) == pytest.approx(0.5)
    assert ks_distance(np.array([0.25, 0.75])) == pytest.approx(0.25)


# ---------- validação e limites ----------

@pytest.mark.parametrize("sample,field", [
    ("abc", "sample"), ([1.0] * 5, "sample"), ([1.0, 2.0, "x"] + [1.0] * 8, "sample"),
    ([1.0] * 9 + [float("nan")], "sample"), ([1.0] * 9 + [float("inf")], "sample"),
    ([1.0] * 9 + [0.0], "sample"), ([1.0] * 9 + [-2.0], "sample"), ([[1.0, 2.0]] * 6, "sample"),
])
def test_invalid_samples(sample, field):
    with pytest.raises(QueueValidationError) as e:
        list(iter_fit(sample))
    assert e.value.field == field


def test_sample_limit_reuses_the_csv_upload_constant():
    assert MAX_SAMPLE_VALUES == MAX_UPLOAD_BYTES // 2
    with pytest.raises(QueueValidationError, match="5.242.881"):
        list(iter_fit(np.ones(MAX_SAMPLE_VALUES + 1)))


def test_bootstrap_validation_and_work_cap():
    for bad, field in [(10, "bootstrap"), (2001, "bootstrap"), (True, "bootstrap"), (1.5, "bootstrap")]:
        with pytest.raises(QueueValidationError) as e:
            validate_bootstrap(bad, 100)
        assert e.value.field == field
    assert validate_bootstrap(0, 100) == (0, None) and validate_bootstrap(20, 100)[0] == 20
    big = MAX_FIT_WORK // 100 + 1
    with pytest.raises(QueueValidationError, match="no máximo 99 réplicas"):
        validate_bootstrap(200, big)
    # Padrão: 200 quando cabe; reduz com aviso; e 0 com aviso quando nem 20 cabem.
    assert validate_bootstrap(None, 1000) == (200, None)
    b, warning = validate_bootstrap(None, 100_000)
    assert b == 80 and "reduzido de 200 para 80" in warning
    b, warning = validate_bootstrap(None, 1_000_000)
    assert b == 0 and "não foi calculado" in warning


@pytest.mark.parametrize("kwargs,field", [({"alpha": 0}, "alpha"), ({"alpha": 1.5}, "alpha"),
                                          ({"kind": "x"}, "kind"), ({"seed": -1}, "seed")])
def test_invalid_options(kwargs, field):
    with pytest.raises(QueueValidationError) as e:
        list(iter_fit([1.0 + i / 10 for i in range(20)], **kwargs))
    assert e.value.field == field


def test_small_sample_warning():
    r = fit_sample([1.0 + i / 7 for i in range(15)], bootstrap=0, seed=1)
    assert any("Amostra pequena" in w for w in r["warnings"])


# ---------- eventos de streaming ----------

def test_events_order_and_progress():
    events = list(iter_fit(draw("weibull", 200, 1), bootstrap=20, seed=1))
    assert [e["type"] for e in events] == ["start"] + ["candidate"] * 5 + ["done"]
    assert events[0]["total"] == 5 and events[0]["bootstrap"] == 20 and events[0]["seed"] == 1
    assert [e["completed"] for e in events[1:6]] == [1, 2, 3, 4, 5]
    assert [e["candidate"]["key"] for e in events[1:6]] == list(CANDIDATE_KEYS)
    assert events[-1]["result"]["n"] == 200


def test_validation_error_comes_before_the_first_event():
    gen = iter_fit([1.0] * 3)
    with pytest.raises(QueueValidationError):
        next(gen)


def test_result_has_histogram_and_curves_for_plotting():
    r = fit_sample(draw("lognormal", 500, 1).tolist(), bootstrap=0, seed=1)
    h = r["histogram"]
    assert len(h["edges"]) == len(h["counts"]) + 1 and sum(h["counts"]) == 500
    assert sum(d * (h["edges"][i + 1] - h["edges"][i]) for i, d in enumerate(h["density"])) == pytest.approx(1.0)
    t = r["curves"]["t"]
    assert len(t) == fit_module.CURVE_POINTS and set(r["curves"]["pdf"]) == set(CANDIDATE_KEYS)
    assert all(len(v) == len(t) for v in r["curves"]["pdf"].values())
    area = np.trapezoid(r["curves"]["pdf"]["lognormal"], t)
    assert area == pytest.approx(1.0, abs=0.03)


# ---------- calibração do p-valor (exigência da D-02): lenta ----------
# Medido (n = 50, B = 200, 400 amostras por família): rejeição a 5 % entre 4,0 % e 5,2 %
# (exp 4,0; Erlang 4,8; lognormal 5,2; Weibull 4,0; uniforme 4,5) e, a 10 %, entre 8,7 % e 11,5 %.
# Com n = 200 e 300 amostras: 3,3 % a 6,0 % (5 %) e 7,7 % a 12,7 % (10 %). Erro-padrão com R = 300 ≈ 1,3 ponto.
# O KS "simples" com parâmetros estimados rejeitou só 0 % a 0,3 % nas quatro famílias de suporte infinito.

@pytest.mark.slow
@pytest.mark.parametrize("key", list(TRUE))
def test_p_value_is_calibrated_under_the_true_distribution(key):
    fam = FAMILIES[key]
    R, N, B = 300, 50, 200
    rejected = naive = 0
    for r in range(R):
        x = np.sort(fam.sample(np.random.default_rng([2026, 17, r]), N, TRUE[key]))
        params = fam.fit(x, _stats(x))
        d = ks_distance(fam.cdf(x, params))
        rejected += bootstrap_p_value(fam, x, params, d, B, np.random.default_rng([7, r])) <= 0.05
        naive += stats.kstwobign.sf(d * math.sqrt(N)) <= 0.05
    rate = rejected / R
    assert 0.01 <= rate <= 0.10, f"{key}: taxa de rejeição {rate:.3f} fora de [0,01; 0,10]"
    if key != "uniform":
        assert naive / R < 0.02                  # o KS simples quase nunca rejeita (a falha que a D-02 evita)
