"""Fixtures de persistência: os testes do histórico rodam em SQLite (sempre) e em
PostgreSQL real, quando QSIMULADOR_TEST_POSTGRES_URL estiver definida."""

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.persistence.config import normalize_database_url
from app.persistence.database import Database, create_db_engine
from app.persistence.models import Base

POSTGRES_ENV_VAR = "QSIMULADOR_TEST_POSTGRES_URL"
BACKEND_DIR = Path(__file__).resolve().parents[1]


def alembic_config(url: str) -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(params=["sqlite", "postgres"])
def database(request) -> Database:
    if request.param == "sqlite":
        engine = create_db_engine("sqlite://")
        Base.metadata.create_all(engine)
        yield Database(engine)
        engine.dispose()
        return

    raw = os.getenv(POSTGRES_ENV_VAR)
    if not raw:
        pytest.skip(f"defina {POSTGRES_ENV_VAR} para testar com PostgreSQL real")
    url = normalize_database_url(raw)
    engine = create_db_engine(url)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS saved_records, alembic_version"))
    command.upgrade(alembic_config(url), "head")  # exercita a migração também
    yield Database(engine)
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS saved_records, alembic_version"))
    engine.dispose()
