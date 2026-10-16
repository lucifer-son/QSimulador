import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.persistence.config import PersistenceLimits
from app.persistence.database import Database, create_db_engine

CLIENT_A = str(uuid.uuid4())
CLIENT_B = str(uuid.uuid4())

PARAMS = {"lambda": 40, "mu": 50.5, "replications": 10, "seed": None, "modelo": "M/M/1"}
RESULT = {
    "rho": 0.1 + 0.2,
    "tiny": 1e-9,
    "big": 12345678.123456789,
    "inteiro": 7,
    "flag": True,
    "nulo": None,
    "texto": "ação — λ ≤ μ",
    "lista": [1, 2.5, [3, {"x": 4}]],
    "aninhado": {"a": {"b": {"c": [0.1, 0.2]}}},
}


def body(**over):
    data = {"kind": "simulation", "title": "M/M/1 base", "params": PARAMS, "result": RESULT, "app_version": "1.4.0"}
    data.update(over)
    return data


def headers(client_id=CLIENT_A):
    return {"X-Client-Id": client_id}


@pytest.fixture
def client(database) -> TestClient:
    return TestClient(create_app(database=database))


def save(client, client_id=CLIENT_A, **over):
    r = client.post("/api/records", json=body(**over), headers=headers(client_id))
    assert r.status_code == 201, r.text
    return r.json()


class TestSalvarEReabrir:
    def test_salva_e_devolve_o_registro(self, client):
        data = save(client)
        assert uuid.UUID(data["id"])
        assert data["kind"] == "simulation"
        assert data["title"] == "M/M/1 base"
        assert data["app_version"] == "1.4.0"
        assert data["size_bytes"] > 0
        assert data["created_at"] and data["updated_at"]

    def test_reabrir_recupera_exatamente_os_dados_gravados(self, client):
        saved = save(client)
        r = client.get(f"/api/records/{saved['id']}", headers=headers())
        assert r.status_code == 200
        got = r.json()
        assert got["params"] == PARAMS
        assert got["result"] == RESULT
        assert got["result"]["rho"] == 0.1 + 0.2  # float idêntico, sem arredondamento
        assert got["result"]["big"] == 12345678.123456789

    def test_titulo_e_aparado(self, client):
        assert save(client, title="  Meu teste  ")["title"] == "Meu teste"

    def test_app_version_e_opcional(self, client):
        data = body()
        data.pop("app_version")
        r = client.post("/api/records", json=data, headers=headers())
        assert r.status_code == 201
        assert r.json()["app_version"] is None

    @pytest.mark.parametrize("kind", ["model", "simulation", "comparison", "experiment", "realdata"])
    def test_aceita_todos_os_tipos(self, client, kind):
        assert save(client, kind=kind)["kind"] == kind


class TestListar:
    def test_lista_vazia(self, client):
        r = client.get("/api/records", headers=headers())
        assert r.status_code == 200
        assert r.json() == {"items": [], "total": 0, "limit": 20, "offset": 0}

    def test_mais_recentes_primeiro_e_sem_params_nem_result(self, client):
        ids = [save(client, title=f"R{i}")["id"] for i in range(3)]
        data = client.get("/api/records", headers=headers()).json()
        assert [i["id"] for i in data["items"]] == ids[::-1]
        assert data["total"] == 3
        assert "params" not in data["items"][0] and "result" not in data["items"][0]

    def test_paginacao(self, client):
        ids = [save(client, title=f"R{i}")["id"] for i in range(5)]
        page1 = client.get("/api/records?limit=2&offset=0", headers=headers()).json()
        page2 = client.get("/api/records?limit=2&offset=2", headers=headers()).json()
        page3 = client.get("/api/records?limit=2&offset=4", headers=headers()).json()
        assert [i["id"] for i in page1["items"]] == ids[::-1][0:2]
        assert [i["id"] for i in page2["items"]] == ids[::-1][2:4]
        assert [i["id"] for i in page3["items"]] == ids[::-1][4:]
        assert page1["total"] == page2["total"] == page3["total"] == 5

    def test_filtro_por_tipo(self, client):
        save(client, kind="simulation")
        save(client, kind="experiment")
        save(client, kind="experiment")
        data = client.get("/api/records?kind=experiment", headers=headers()).json()
        assert data["total"] == 2
        assert {i["kind"] for i in data["items"]} == {"experiment"}

    @pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "kind=outro"])
    def test_parametros_invalidos(self, client, query):
        r = client.get(f"/api/records?{query}", headers=headers())
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_request"


class TestIsolamentoPorNavegador:
    def test_cada_navegador_so_ve_os_proprios_registros(self, client):
        a = save(client, CLIENT_A, title="de A")
        save(client, CLIENT_B, title="de B")
        assert [i["title"] for i in client.get("/api/records", headers=headers(CLIENT_A)).json()["items"]] == ["de A"]
        assert [i["title"] for i in client.get("/api/records", headers=headers(CLIENT_B)).json()["items"]] == ["de B"]
        assert client.get(f"/api/records/{a['id']}", headers=headers(CLIENT_B)).status_code == 404

    def test_outro_navegador_nao_renomeia_nem_exclui(self, client):
        a = save(client, CLIENT_A)
        assert client.patch(f"/api/records/{a['id']}", json={"title": "x"}, headers=headers(CLIENT_B)).status_code == 404
        assert client.delete(f"/api/records/{a['id']}", headers=headers(CLIENT_B)).status_code == 404
        assert client.get(f"/api/records/{a['id']}", headers=headers(CLIENT_A)).json()["title"] == "M/M/1 base"

    def test_cabecalho_ausente(self, client):
        r = client.get("/api/records")
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_client_id"

    @pytest.mark.parametrize("value", ["abc", "123", "not-a-uuid"])
    def test_cabecalho_que_nao_e_uuid(self, client, value):
        r = client.get("/api/records", headers={"X-Client-Id": value})
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_client_id"

    def test_uuid_e_normalizado(self, client):
        save(client, CLIENT_A.upper())
        assert client.get("/api/records", headers=headers(CLIENT_A)).json()["total"] == 1


class TestRenomearEExcluir:
    def test_renomear(self, client):
        saved = save(client)
        r = client.patch(f"/api/records/{saved['id']}", json={"title": "Novo nome"}, headers=headers())
        assert r.status_code == 200
        assert r.json()["title"] == "Novo nome"
        assert r.json()["updated_at"] >= saved["created_at"]
        again = client.get(f"/api/records/{saved['id']}", headers=headers()).json()
        assert again["title"] == "Novo nome"
        assert again["result"] == RESULT  # renomear não altera os dados

    @pytest.mark.parametrize("title", ["", "   ", "x" * 121])
    def test_titulo_invalido(self, client, title):
        saved = save(client)
        r = client.patch(f"/api/records/{saved['id']}", json={"title": title}, headers=headers())
        assert r.status_code == 422

    def test_excluir(self, client):
        saved = save(client)
        assert client.delete(f"/api/records/{saved['id']}", headers=headers()).status_code == 204
        assert client.get(f"/api/records/{saved['id']}", headers=headers()).status_code == 404
        assert client.delete(f"/api/records/{saved['id']}", headers=headers()).status_code == 404
        assert client.get("/api/records", headers=headers()).json()["total"] == 0

    def test_registro_inexistente(self, client):
        missing = str(uuid.uuid4())
        for call in (
            client.get(f"/api/records/{missing}", headers=headers()),
            client.patch(f"/api/records/{missing}", json={"title": "x"}, headers=headers()),
            client.delete(f"/api/records/{missing}", headers=headers()),
        ):
            assert call.status_code == 404
            assert call.json() == {"code": "record_not_found", "message": "Registro não encontrado."}

    def test_id_que_nao_e_uuid(self, client):
        assert client.get("/api/records/abc", headers=headers()).status_code == 422


class TestValidacao:
    @pytest.mark.parametrize(
        "over",
        [
            {"kind": "outro"},
            {"title": ""},
            {"title": "   "},
            {"title": "x" * 121},
            {"params": "texto"},
            {"result": [1, 2]},
            {"app_version": "v" * 33},
        ],
    )
    def test_corpo_invalido(self, client, over):
        r = client.post("/api/records", json=body(**over), headers=headers())
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_request"

    def test_campos_obrigatorios(self, client):
        r = client.post("/api/records", json={"kind": "model"}, headers=headers())
        assert r.status_code == 422
        assert {f["field"] for f in r.json()["fields"]} >= {"title", "params", "result"}

    def test_valores_nao_finitos_sao_recusados(self, client):
        raw = '{"kind":"model","title":"x","params":{},"result":{"a":NaN}}'
        r = client.post("/api/records", content=raw, headers={**headers(), "Content-Type": "application/json"})
        assert r.status_code == 422
        assert r.json()["code"] == "invalid_record"


class TestLimites:
    def test_registro_grande_demais(self, database):
        app = create_app(database=database, limits=PersistenceLimits(max_record_bytes=200))
        c = TestClient(app)
        ok = c.post("/api/records", json=body(params={}, result={"a": 1}), headers=headers())
        assert ok.status_code == 201
        big = c.post("/api/records", json=body(result={"texto": "x" * 500}), headers=headers())
        assert big.status_code == 413
        assert big.json()["code"] == "record_too_large"

    def test_limite_de_registros_por_navegador(self, database):
        c = TestClient(create_app(database=database, limits=PersistenceLimits(max_records_per_client=2)))
        first = c.post("/api/records", json=body(), headers=headers()).json()
        assert c.post("/api/records", json=body(), headers=headers()).status_code == 201
        full = c.post("/api/records", json=body(), headers=headers())
        assert full.status_code == 409
        assert full.json()["code"] == "record_limit_reached"
        # outro navegador não é afetado; excluir libera espaço
        assert c.post("/api/records", json=body(), headers=headers(CLIENT_B)).status_code == 201
        assert c.delete(f"/api/records/{first['id']}", headers=headers()).status_code == 204
        assert c.post("/api/records", json=body(), headers=headers()).status_code == 201


class TestPersistenciaDesativada:
    @pytest.fixture
    def off(self, monkeypatch):
        for name in ("QSIMULADOR_DATABASE_URL", "DATABASE_URL"):
            monkeypatch.delenv(name, raising=False)
        return TestClient(create_app())

    def test_status(self, off):
        data = off.get("/api/records/status").json()
        assert data["enabled"] is False

    def test_rotas_respondem_503(self, off):
        missing = str(uuid.uuid4())
        calls = [
            off.get("/api/records", headers=headers()),
            off.post("/api/records", json=body(), headers=headers()),
            off.get(f"/api/records/{missing}", headers=headers()),
            off.patch(f"/api/records/{missing}", json={"title": "x"}, headers=headers()),
            off.delete(f"/api/records/{missing}", headers=headers()),
        ]
        for r in calls:
            assert r.status_code == 503
            assert r.json()["code"] == "persistence_disabled"

    def test_o_nucleo_continua_funcionando(self, off):
        r = off.post("/api/models/mm1/calculate", json={"lambda": 40, "mu": 50})
        assert r.status_code == 200
        assert off.get("/api/health").json() == {"status": "ok", "persistence": "disabled"}


class TestBancoIndisponivel:
    def test_503_quando_nao_conecta(self, tmp_path):
        engine = create_db_engine(f"sqlite:///{tmp_path}/nao/existe/q.db")
        c = TestClient(create_app(database=Database(engine)))
        r = c.get("/api/records", headers=headers())
        assert r.status_code == 503
        assert r.json()["code"] == "database_unavailable"


class TestMigracaoEsquecida:
    def test_tabela_inexistente_vira_503_com_orientacao(self, database):
        from sqlalchemy import text

        with database.engine.begin() as conn:
            conn.execute(text("DROP TABLE saved_records"))
        c = TestClient(create_app(database=database))
        for r in (
            c.get("/api/records", headers=headers()),
            c.post("/api/records", json=body(), headers=headers()),
        ):
            assert r.status_code == 503
            assert r.json()["code"] == "database_unavailable"
            assert "alembic upgrade head" in r.json()["message"]


class TestStatusEHealth:
    def test_status_ativado_com_limites(self, database):
        c = TestClient(create_app(database=database, limits=PersistenceLimits(1000, 5)))
        assert c.get("/api/records/status").json() == {
            "enabled": True, "max_record_bytes": 1000, "max_records_per_client": 5,
        }

    def test_health_informa_persistencia(self, database):
        assert TestClient(create_app(database=database)).get("/api/health").json() == {
            "status": "ok", "persistence": "enabled",
        }


class TestCors:
    ORIGIN = "https://qsimulador.exemplo.com"

    @pytest.mark.parametrize("method", ["DELETE", "PATCH", "POST"])
    def test_preflight_com_x_client_id(self, method, database):
        c = TestClient(create_app([self.ORIGIN], database=database))
        r = c.options(
            f"/api/records/{uuid.uuid4()}",
            headers={
                "Origin": self.ORIGIN,
                "Access-Control-Request-Method": method,
                "Access-Control-Request-Headers": "content-type,x-client-id",
            },
        )
        assert r.status_code == 200
        assert method in r.headers["access-control-allow-methods"]
        assert "x-client-id" in r.headers["access-control-allow-headers"].lower()
