"""Rotas /api/realdata: análise do CSV do JMeter, recomendação do modelo e comparação."""

from fastapi.testclient import TestClient

from app.domain.validation.realdata import MAX_UPLOAD_BYTES
from app.main import app
from examples.make_jtl import closed_levels_csv, open_rows, to_csv

client = TestClient(app)

ANALYZE = "/api/realdata/analyze"
COMPARE = "/api/realdata/compare"


def enviar(csv: str | bytes, nome: str = "teste.csv", **campos):
    conteudo = csv.encode() if isinstance(csv, str) else csv
    return client.post(ANALYZE, files={"file": (nome, conteudo, "text/csv")},
                       data={k: str(v) for k, v in campos.items()})


def campos(resposta):
    return [item["field"] for item in resposta.json()["fields"]]


FECHADO = closed_levels_csv([1, 6, 24, 60], 1.0, 10.0, 1, 120, 3)


def test_analisa_um_teste_fechado_e_recomenda_populacao_finita():
    r = enviar(FECHADO)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["status"] == "recommended" and corpo["system_type"] == "closed"
    assert corpo["recommended"]["key"] == "mm1n" and corpo["confidence"] == "alta"
    assert [lv["users"] for lv in corpo["levels"]] == [1, 6, 24, 60]
    assert corpo["ranking"][0]["recommended"] is True
    assert "sistema fechado" in corpo["warnings"][0]
    assert {d["id"] for d in corpo["diagnostics"]} == {f"V{i}" for i in range(1, 9)}


def test_contexto_do_usuario_chega_a_analise():
    csv = to_csv(open_rows(14, 10, 1, 8, 300, 2))
    r = enviar(csv, system_type="open", servers=1, service_time_s=0.1, capacity=8)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["recommended"]["key"] == "mm1k" and corpo["recommended"]["capacity"] == 8
    assert corpo["estimates"]["capacity_source"] == "informado"


def test_arquivo_invalido_devolve_422_invalid_dataset_com_o_campo():
    r = enviar("a,b,c\n1,2,3\n")
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_dataset" and campos(r) == ["file"]


def test_extensao_diferente_de_csv_e_rejeitada():
    r = enviar(FECHADO, nome="teste.txt")
    assert r.status_code == 422 and r.json()["code"] == "invalid_dataset"


def test_arquivo_acima_do_limite_devolve_413():
    r = enviar(b"x" * (MAX_UPLOAD_BYTES + 1))
    assert r.status_code == 413 and r.json()["code"] == "file_too_large"


def test_poucas_amostras_devolve_insufficient_sample():
    curto = "\n".join(FECHADO.splitlines()[:15]) + "\n"
    r = enviar(curto)
    assert r.status_code == 422 and r.json()["code"] == "insufficient_sample"


def test_parametro_de_contexto_invalido_identifica_o_campo():
    r = enviar(FECHADO, system_type="talvez")
    assert r.status_code == 422 and campos(r) == ["system_type"]
    r = enviar(FECHADO, servers=0)
    assert r.status_code == 422 and campos(r) == ["servers"]


def test_sem_arquivo_e_invalid_request():
    r = client.post(ANALYZE, data={})
    assert r.status_code == 422 and r.json()["code"] == "invalid_request" and campos(r) == ["file"]


def test_compara_com_outro_modelo_sem_reenviar_o_arquivo():
    niveis = enviar(FECHADO).json()["levels"]
    r = client.post(COMPARE, json={"model": "mm1n", "mu": 10.0, "think_time": 1.0, "levels": niveis})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["notation"] == "M/M/1//N" and len(corpo["comparison"]) == 4
    w = corpo["comparison"][-1]["metrics"]["W"]
    assert abs(w["model"] - w["observed"]) / w["observed"] * 100 == w["relative_error_pct"]


def test_compara_exige_os_parametros_do_modelo():
    niveis = enviar(FECHADO).json()["levels"]
    r = client.post(COMPARE, json={"model": "mm1n", "mu": 10.0, "levels": niveis})
    assert r.status_code == 422 and campos(r) == ["think_time"]
    r = client.post(COMPARE, json={"model": "mm1k", "mu": 10.0, "levels": niveis})
    assert r.status_code == 422 and campos(r) == ["capacity"]


def test_openapi_documenta_as_rotas_novas():
    caminhos = app.openapi()["paths"]
    assert ANALYZE in caminhos and COMPARE in caminhos
