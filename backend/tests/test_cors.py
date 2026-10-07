import pytest
from fastapi.testclient import TestClient

from app.main import create_app, parse_origins

ORIGIN = "https://qsimulador.exemplo.com"
URL = "/api/models/mm1/calculate"
BODY = {"lambda": 40, "mu": 50}


class TestParseOrigins:
    def test_sem_valor_nao_ha_origens(self):
        assert parse_origins(None) == []
        assert parse_origins("") == []
        assert parse_origins(" , ,") == []

    def test_separa_por_virgula_e_remove_espacos(self):
        assert parse_origins(" https://a.com , http://localhost:5173 ,") == ["https://a.com", "http://localhost:5173"]


class TestCors:
    def test_desligado_por_padrao(self):
        client = TestClient(create_app())
        r = client.post(URL, json=BODY, headers={"Origin": ORIGIN})
        assert r.status_code == 200
        assert "access-control-allow-origin" not in r.headers

    def test_origem_permitida_recebe_o_cabecalho(self):
        client = TestClient(create_app([ORIGIN]))
        r = client.post(URL, json=BODY, headers={"Origin": ORIGIN})
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == ORIGIN

    def test_origem_nao_listada_nao_recebe_o_cabecalho(self):
        client = TestClient(create_app([ORIGIN]))
        r = client.post(URL, json=BODY, headers={"Origin": "https://outro.com"})
        assert "access-control-allow-origin" not in r.headers

    def test_preflight_aceita_post_com_json(self):
        client = TestClient(create_app([ORIGIN]))
        r = client.options(URL, headers={
            "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        })
        assert r.status_code == 200
        assert r.headers["access-control-allow-origin"] == ORIGIN
        assert "POST" in r.headers["access-control-allow-methods"]

    def test_preflight_de_origem_nao_listada_e_recusado(self):
        client = TestClient(create_app([ORIGIN]))
        r = client.options(URL, headers={"Origin": "https://outro.com", "Access-Control-Request-Method": "POST"})
        assert r.status_code == 400

    def test_erros_da_api_tambem_levam_o_cabecalho(self):
        client = TestClient(create_app([ORIGIN]))
        r = client.post(URL, json={"lambda": 60, "mu": 50}, headers={"Origin": ORIGIN})
        assert r.status_code == 422
        assert r.headers["access-control-allow-origin"] == ORIGIN

    @pytest.mark.parametrize("path", ["/api/health", "/openapi.json"])
    def test_a_aplicacao_continua_a_mesma_com_cors(self, path):
        assert TestClient(create_app([ORIGIN])).get(path).status_code == 200
