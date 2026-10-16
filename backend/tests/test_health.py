from fastapi.testclient import TestClient

from app.main import create_app


def test_health(monkeypatch):
    for name in ("QSIMULADOR_DATABASE_URL", "DATABASE_URL"):
        monkeypatch.delenv(name, raising=False)
    response = TestClient(create_app()).get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "persistence": "disabled"}
