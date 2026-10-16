"""Configuração da persistência, lida de variáveis de ambiente (RNF-26)."""

import os
from dataclasses import dataclass

DATABASE_URL_ENV_VARS = ("QSIMULADOR_DATABASE_URL", "DATABASE_URL")
MAX_RECORD_BYTES_ENV_VAR = "QSIMULADOR_MAX_RECORD_BYTES"
MAX_RECORDS_ENV_VAR = "QSIMULADOR_MAX_RECORDS_PER_CLIENT"

DEFAULT_MAX_RECORD_BYTES = 2_000_000
DEFAULT_MAX_RECORDS_PER_CLIENT = 200


def normalize_database_url(url: str) -> str:
    """Aceita as formas comuns de URL do PostgreSQL e escolhe o driver psycopg 3.

    Provedores como Neon e Supabase entregam `postgres://...` ou `postgresql://...`;
    o SQLAlchemy precisa de `postgresql+psycopg://...`.
    """
    url = url.strip()
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def database_url_from_env() -> str | None:
    for name in DATABASE_URL_ENV_VARS:
        value = os.getenv(name)
        if value and value.strip():
            return normalize_database_url(value)
    return None


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value > 0 else default


@dataclass(frozen=True)
class PersistenceLimits:
    max_record_bytes: int = DEFAULT_MAX_RECORD_BYTES
    max_records_per_client: int = DEFAULT_MAX_RECORDS_PER_CLIENT

    @classmethod
    def from_env(cls) -> "PersistenceLimits":
        return cls(
            max_record_bytes=_int_from_env(MAX_RECORD_BYTES_ENV_VAR, DEFAULT_MAX_RECORD_BYTES),
            max_records_per_client=_int_from_env(MAX_RECORDS_ENV_VAR, DEFAULT_MAX_RECORDS_PER_CLIENT),
        )
