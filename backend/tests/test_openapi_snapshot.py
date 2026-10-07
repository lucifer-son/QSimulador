"""Garante que frontend/openapi.json (de onde saem os tipos TypeScript) acompanha a API."""

import json
from pathlib import Path

import pytest

from app.main import app

SNAPSHOT = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


@pytest.mark.skipif(not SNAPSHOT.exists(), reason="pasta frontend/ ausente")
def test_openapi_do_frontend_esta_atualizado():
    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    assert app.openapi() == saved, (
        "A API mudou e frontend/openapi.json ficou desatualizado. "
        "Em backend/: python -m scripts.export_openapi   e, em frontend/: npm run gen:api"
    )
