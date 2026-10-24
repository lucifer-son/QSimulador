"""Resolução de cenários: sobrescritas absolutas e relativas, troca de modelo e erros com o campo."""

import pytest

from app.domain.validation.errors import QueueValidationError
from app.scenarios.spec import (
    BaseSpec, Override, ScenarioSpec, changes, resolve_base, resolve_scenario,
)

ABS, REL = "absolute", "relative"


def base_mmc():
    return resolve_base(BaseSpec("mmc", 8.0, mu=1.0, servers=10))


def base_mg1():
    return resolve_base(BaseSpec("mg1", 5.0, service=("lognormal", {"mean": 0.1, "cv": 1.5})))


def field_of(base, spec, index=2):
    with pytest.raises(QueueValidationError) as info:
        resolve_scenario(base, spec, index)
    return info.value.field


def test_relativo_e_absoluto():
    b = base_mmc()
    s = resolve_scenario(b, ScenarioSpec(lam=Override(REL, 20), servers=Override(REL, 1)), 0)
    assert (s.lam, s.servers, s.name) == (pytest.approx(9.6), 11, "Cenário 1")
    s = resolve_scenario(b, ScenarioSpec(name=" Pico ", lam=Override(ABS, 12), mu=Override(REL, -30)), 0)
    assert s.name == "Pico" and s.lam == 12.0
    assert s.parameters()["mu"] == 0.7          # sem ruído de ponto flutuante


def test_a_base_nao_e_alterada():
    b = base_mmc()
    resolve_scenario(b, ScenarioSpec(lam=Override(REL, 50), servers=Override(ABS, 3)), 0)
    assert (b.lam, b.servers, b.name) == (8.0, 10, "Base")


def test_cv_e_k_do_servico_geral():
    s = resolve_scenario(base_mg1(), ScenarioSpec(cv=Override(REL, 50)), 0)
    assert s.service.cv == pytest.approx(2.25) and s.service.mean == pytest.approx(0.1)
    erl = resolve_base(BaseSpec("mg1", 5.0, service=("erlang", {"mean": 0.1, "k": 4})))
    s = resolve_scenario(erl, ScenarioSpec(k=Override(REL, 2)), 0)
    assert s.service.parameters["k"] == 6 and s.service.mean == pytest.approx(0.1)


def test_mu_reescala_preservando_o_cv():
    s = resolve_scenario(base_mg1(), ScenarioSpec(mu=Override(REL, 100)), 0)
    assert s.service.mean == pytest.approx(0.05) and s.service.cv == pytest.approx(1.5)


def test_troca_de_modelo():
    b = base_mmc()
    assert resolve_scenario(b, ScenarioSpec(model="mm1"), 0).servers == 1
    erl = resolve_scenario(b, ScenarioSpec(model="erlangb"), 0)
    assert erl.capacity is None and erl.sim_capacity == 10
    k = resolve_scenario(b, ScenarioSpec(model="mmck", capacity=Override(ABS, 20)), 0)
    assert k.capacity == 20
    gen = resolve_scenario(b, ScenarioSpec(model="mgc", service=("lognormal", {"mean": 1.0, "cv": 2.0})), 0)
    assert gen.service.cv == pytest.approx(2.0)
    # de M/G para markoviano: serviço exponencial com a mesma média
    back = resolve_scenario(base_mg1(), ScenarioSpec(model="mm1"), 0)
    assert back.service.key == "exponential" and back.service.mean == pytest.approx(0.1)


def test_campos_dos_erros():
    b = base_mmc()
    assert field_of(b, ScenarioSpec(cv=Override(ABS, 2))) == "scenarios[2].cv"
    assert field_of(b, ScenarioSpec(service=("lognormal", {"mean": 1.0, "cv": 1.0}))) == "scenarios[2].service"
    assert field_of(b, ScenarioSpec(model="mm1", servers=Override(ABS, 2))) == "scenarios[2].servers"
    assert field_of(b, ScenarioSpec(servers=Override(ABS, 2.5))) == "scenarios[2].servers"
    assert field_of(b, ScenarioSpec(model="mmck")) == "scenarios[2].capacity"
    assert field_of(b, ScenarioSpec(capacity=Override(ABS, 5))) == "scenarios[2].capacity"
    assert field_of(b, ScenarioSpec(model="mmck", capacity=Override(ABS, 5))) == "scenarios[2].capacity"
    assert field_of(b, ScenarioSpec(lam=Override(REL, -100))) == "scenarios[2].lambda"
    assert field_of(b, ScenarioSpec(lam=Override("x", 1))) == "scenarios[2].lambda"
    assert field_of(b, ScenarioSpec(model="xyz")) == "scenarios[2].model"
    assert field_of(base_mg1(), ScenarioSpec(k=Override(ABS, 2))) == "scenarios[2].k"
    assert field_of(base_mg1(), ScenarioSpec(cv=Override(ABS, 50))) == "scenarios[2].cv"
    assert field_of(b, ScenarioSpec(name="x" * 61)) == "scenarios[2].name"


def test_relativo_exige_valor_na_base():
    assert field_of(base_mmc(), ScenarioSpec(model="mmck", capacity=Override(REL, 2))) == "scenarios[2].capacity"


def test_erros_da_base_comecam_com_base():
    for spec in (BaseSpec("mmc", 8.0, mu=1.0), BaseSpec("mmc", -1.0, mu=1.0, servers=2),
                 BaseSpec("mg1", 5.0), BaseSpec("mmck", 5.0, mu=1.0, servers=2)):
        with pytest.raises(QueueValidationError) as info:
            resolve_base(spec)
        assert info.value.field.startswith("base.")


def test_lista_de_mudancas():
    b = base_mmc()
    s = resolve_scenario(b, ScenarioSpec(lam=Override(REL, 20), servers=Override(REL, 1)), 0)
    assert changes(b, s) == [
        {"field": "lambda", "from_value": 8.0, "to_value": pytest.approx(9.6)},
        {"field": "servers", "from_value": 10, "to_value": 11},
    ]
    assert changes(b, resolve_scenario(b, ScenarioSpec(), 0)) == []
