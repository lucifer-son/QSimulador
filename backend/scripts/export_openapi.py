"""Exporta o esquema OpenAPI da API para o frontend gerar os tipos TypeScript.

Uso (a partir da pasta backend/, com o ambiente virtual ativo):

    python -m scripts.export_openapi

Grava ../frontend/openapi.json. Depois, em frontend/: npm run gen:api
"""

import json
from pathlib import Path

from app.main import app

DESTINO = Path(__file__).resolve().parents[2] / "frontend" / "openapi.json"


def main() -> None:
    DESTINO.write_text(
        json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"OpenAPI gravado em {DESTINO}")


if __name__ == "__main__":
    main()
