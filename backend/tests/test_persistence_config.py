import pytest
from alembic import command
from sqlalchemy import create_engine, inspect

from app.persistence.config import (
    DEFAULT_MAX_RECORD_BYTES,
    DEFAULT_MAX_RECORDS_PER_CLIENT,
    PersistenceLimits,
    database_url_from_env,
    normalize_database_url,
)
from tests.conftest import alembic_config


class TestNormalizeDatabaseUrl:
    @pytest.mark.parametrize(
        "entrada, esperado",
        [
            ("postgres://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
            ("postgresql://u:p@host/db?sslmode=require", "postgresql+psycopg://u:p@host/db?sslmode=require"),
            ("postgresql+psycopg://u:p@host/db", "postgresql+psycopg://u:p@host/db"),
            ("  postgres://u@h/d  ", "postgresql+psycopg://u@h/d"),
            ("sqlite:///x.db", "sqlite:///x.db"),
        ],
    )
    def test_normaliza(self, entrada, esperado):
        assert normalize_database_url(entrada) == esperado


class TestDatabaseUrlFromEnv:
    def test_sem_variaveis(self, monkeypatch):
        monkeypatch.delenv("QSIMULADOR_DATABASE_URL", raising=False)
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert database_url_from_env() is None

    def test_vazia_conta_como_ausente(self, monkeypatch):
        monkeypatch.setenv("QSIMULADOR_DATABASE_URL", "   ")
        monkeypatch.delenv("DATABASE_URL", raising=False)
        assert database_url_from_env() is None

    def test_database_url_e_aceita(self, monkeypatch):
        monkeypatch.delenv("QSIMULADOR_DATABASE_URL", raising=False)
        monkeypatch.setenv("DATABASE_URL", "postgres://u@h/d")
        assert database_url_from_env() == "postgresql+psycopg://u@h/d"

    def test_variavel_propria_tem_prioridade(self, monkeypatch):
        monkeypatch.setenv("QSIMULADOR_DATABASE_URL", "postgres://a@h/a")
        monkeypatch.setenv("DATABASE_URL", "postgres://b@h/b")
        assert database_url_from_env() == "postgresql+psycopg://a@h/a"


class TestLimitsFromEnv:
    def test_padroes(self, monkeypatch):
        monkeypatch.delenv("QSIMULADOR_MAX_RECORD_BYTES", raising=False)
        monkeypatch.delenv("QSIMULADOR_MAX_RECORDS_PER_CLIENT", raising=False)
        limits = PersistenceLimits.from_env()
        assert limits.max_record_bytes == DEFAULT_MAX_RECORD_BYTES
        assert limits.max_records_per_client == DEFAULT_MAX_RECORDS_PER_CLIENT

    def test_valores_validos(self, monkeypatch):
        monkeypatch.setenv("QSIMULADOR_MAX_RECORD_BYTES", "5000")
        monkeypatch.setenv("QSIMULADOR_MAX_RECORDS_PER_CLIENT", "7")
        assert PersistenceLimits.from_env() == PersistenceLimits(5000, 7)

    @pytest.mark.parametrize("valor", ["abc", "0", "-3", "1.5"])
    def test_valores_invalidos_voltam_ao_padrao(self, monkeypatch, valor):
        monkeypatch.setenv("QSIMULADOR_MAX_RECORD_BYTES", valor)
        monkeypatch.setenv("QSIMULADOR_MAX_RECORDS_PER_CLIENT", valor)
        assert PersistenceLimits.from_env() == PersistenceLimits()


def test_migracao_sobe_e_desce(tmp_path):
    url = f"sqlite:///{tmp_path}/mig.db"
    config = alembic_config(url)
    command.upgrade(config, "head")
    inspector = inspect(create_engine(url))
    assert "saved_records" in inspector.get_table_names()
    colunas = {c["name"] for c in inspector.get_columns("saved_records")}
    assert colunas == {
        "id", "client_id", "kind", "title", "app_version", "params", "result",
        "size_bytes", "created_at", "updated_at",
    }
    command.downgrade(config, "base")
    assert "saved_records" not in inspect(create_engine(url)).get_table_names()
