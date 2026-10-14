"""Verificação dos dados e recomendação do modelo (requisito da professora, Fase 7).

A validação é estatística, como no restante do projeto (RNF-02): os dados são gerados a
partir de um modelo conhecido, com 30 sementes, e exige-se que o modelo verdadeiro seja o
recomendado em pelo menos 90 % delas. Nunca se compara um valor aleatório exato.
"""

import json

import pytest

from app.domain.validation.errors import (
    InsufficientSampleError, InvalidDatasetError, QueueValidationError,
)
from app.domain.validation.realdata import build_context
from app.realdata.jmeter import parse_jtl
from app.realdata.recommendation import analyze
from examples.make_jtl import closed_levels_csv, closed_rows, open_rows, to_csv

SEMENTES = range(1, 31)
ABERTO = {"system_type": "open", "servers": 1, "service_time_s": 0.1}

CENARIOS = {
    # modelo verdadeiro -> (gerador(semente), contexto informado pelo usuário)
    "mm1n": (lambda s: closed_levels_csv([1, 6, 24, 60], 1.0, 10.0, 1, 120, s), {}),
    "mmcn": (lambda s: closed_levels_csv([1, 8, 32, 100], 1.0, 5.0, 4, 120, s), {}),
    "mm1": (lambda s: to_csv(open_rows(6, 10, 1, None, 300, s)), ABERTO),
    "mmc": (lambda s: to_csv(open_rows(20, 10, 3, None, 300, s)), {**ABERTO, "servers": 3}),
    "mm1k": (lambda s: to_csv(open_rows(14, 10, 1, 8, 300, s)), ABERTO),
    "mmck": (lambda s: to_csv(open_rows(40, 10, 3, 6, 300, s)), {**ABERTO, "servers": 3}),
}


def rodar(csv: str, **contexto):
    return analyze(parse_jtl(csv), build_context(**contexto))


@pytest.mark.parametrize("verdadeiro", list(CENARIOS))
def test_recomenda_o_modelo_verdadeiro_em_pelo_menos_90_por_cento_das_sementes(verdadeiro):
    gerar, contexto = CENARIOS[verdadeiro]
    acertos = sum(
        (r := rodar(gerar(s), **contexto)).recommended is not None and r.recommended["key"] == verdadeiro
        for s in SEMENTES
    )
    assert acertos >= 27, f"{verdadeiro}: {acertos}/30"


def test_um_unico_nivel_sem_tempo_de_servico_e_autoconsistente_e_tem_confianca_baixa():
    r = rodar(to_csv(closed_rows(20, 1.0, 10.0, 1, 400, 1)))
    assert r.recommended["key"] == "mm1n"
    assert r.estimates.autoconsistent and r.estimates.mu_source == "autoconsistente"
    assert r.confidence == "baixa"
    # O tempo de resposta não pode validar um μ calibrado por ele mesmo.
    assert r.comparison[0]["metrics"]["W"]["relative_error_pct"] < 1e-6


def test_varios_niveis_estimam_mu_c_e_z_sem_ajuda():
    gerar, _ = CENARIOS["mmcn"]
    r = rodar(gerar(7))
    e = r.estimates
    assert e.mu_source == "menor_nivel" and e.mu == pytest.approx(5.0, rel=0.25)
    assert (e.servers, e.servers_source) == (4, "estimado")
    assert e.think_time == pytest.approx(1.0, rel=0.1)
    assert r.confidence == "alta"


def test_fechado_traz_o_aviso_de_sistema_fechado_e_indica_populacao_finita():
    r = rodar(CENARIOS["mm1n"][0](3))
    assert r.system_type == "closed"
    assert "sistema fechado" in r.warnings[0] and "M/M/1//N" in r.warnings[0]
    v1 = next(d for d in r.diagnostics if d.id == "V1")
    assert "allThreads" in v1.evidence


def test_aberto_com_rejeicoes_descarta_capacidade_infinita_e_explica_o_motivo():
    gerar, contexto = CENARIOS["mm1k"]
    r = rodar(gerar(2), **contexto)
    mm1 = next(x for x in r.ranking if x["key"] == "mm1")
    assert not mm1["eligible"] and any("rejeições" in motivo for motivo in mm1["reasons"])
    assert r.estimates.capacity == 8 and r.estimates.capacity_source == "estimado"
    assert any(w.startswith("K foi estimado") for w in r.warnings)


def test_fechado_com_rejeicoes_nao_tem_modelo_no_catalogo():
    linhas = to_csv(closed_rows(20, 1.0, 10.0, 1, 400, 1)).splitlines()
    for i in range(1, len(linhas), 12):    # ~8 % das requisições viram 503
        linhas[i] = linhas[i].replace("200,OK,", "503,Service Unavailable,").replace(",text,true,", ",text,false,")
    r = rodar("\n".join(linhas) + "\n")
    assert r.status == "no_good_fit" and r.recommended is None
    assert r.nearest is not None and r.nearest["key"] == "mm1n"
    assert any("Nenhum modelo do catálogo" in w for w in r.warnings)


def test_sobrecarga_sem_rejeicoes_nao_recomenda_modelo_de_capacidade_infinita():
    r = rodar(to_csv(open_rows(12, 10, 1, None, 300, 2)), **ABERTO)
    assert r.status == "no_good_fit" and r.confidence == "baixa"
    v2 = next(d for d in r.diagnostics if d.id == "V2")
    assert v2.status == "critico"
    assert all(not x["eligible"] for x in r.ranking)
    assert any("sobrecarga" in w.lower() for w in r.warnings)


def test_contexto_do_usuario_substitui_a_inferencia():
    csv = to_csv(closed_rows(20, 1.0, 10.0, 1, 400, 1))
    r = rodar(csv, system_type="open", servers=1, service_time_s=0.1)
    assert r.system_type == "open"
    chaves_elegiveis = {x["key"] for x in r.ranking if x["eligible"]}
    assert not chaves_elegiveis & {"mm1n", "mmcn"}
    assert r.estimates.mu == pytest.approx(10.0) and r.estimates.mu_source == "informado"


def test_filtro_de_label_e_amostras_insuficientes():
    csv = to_csv(closed_rows(20, 1.0, 10.0, 1, 200, 1))
    with pytest.raises(InvalidDatasetError) as erro:
        rodar(csv, labels=["não existe"])
    assert erro.value.field == "labels"
    curto = "\n".join(csv.splitlines()[:11]) + "\n"
    with pytest.raises(InsufficientSampleError):
        rodar(curto)


def test_comparacao_usa_o_erro_relativo_ao_observado():
    r = rodar(CENARIOS["mm1n"][0](5))
    w = r.comparison[-1]["metrics"]["W"]
    esperado = abs(w["model"] - w["observed"]) / w["observed"] * 100
    assert w["relative_error_pct"] == pytest.approx(esperado)
    assert w["observed_ci_low"] <= w["observed"] <= w["observed_ci_high"]


def test_resultado_e_json_valido_e_deterministico():
    csv = CENARIOS["mm1n"][0](9)
    a, b = rodar(csv).as_dict(), rodar(csv).as_dict()
    assert a == b
    json.dumps(a, allow_nan=False)   # sem NaN nem infinito
    assert {"status", "confidence", "recommended", "ranking", "rationale", "diagnostics"} <= set(a)


def test_a_justificativa_cita_so_evidencias_calculadas():
    r = rodar(CENARIOS["mm1n"][0](9))
    assert "Recomendado: M/M/1//N" in r.rationale
    assert "1, 6, 24 e 60 usuários" in r.rationale
    assert "não prova" in r.rationale   # limite do alcance da recomendação


@pytest.mark.parametrize(
    "campo, valor",
    [("system_type", "talvez"), ("servers", 0), ("service_time_s", -1), ("think_time_s", -0.5),
     ("trim_start_pct", 60), ("confidence_level", 1.5), ("capacity", 0)],
)
def test_contexto_invalido(campo, valor):
    with pytest.raises(QueueValidationError) as erro:
        build_context(**{campo: valor})
    assert erro.value.field == campo


def test_ranking_decompoe_a_decisao_por_criterio():
    r = rodar(CENARIOS["mmcn"][0](4))
    escolhido = r.ranking[0]
    assert escolhido["recommended"] and escolhido["score_pct"] == pytest.approx(escolhido["error_pct"] + escolhido["penalty_pp"])
    assert {c["id"] for c in escolhido["criteria"]} >= {"estrutura", "capacidade", "servidores", "dados"}
    assert all(c["passed"] for c in escolhido["criteria"])
    descartado = next(x for x in r.ranking if x["key"] == "mm1")
    assert any(not c["passed"] and c["id"] == "estrutura" for c in descartado["criteria"])
