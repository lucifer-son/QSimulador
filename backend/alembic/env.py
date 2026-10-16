"""Ambiente do Alembic: lê a URL do banco das variáveis de ambiente."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.persistence.config import database_url_from_env
from app.persistence.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _url() -> str:
    url = config.get_main_option("sqlalchemy.url") or database_url_from_env()
    if not url:
        raise SystemExit(
            "Defina QSIMULADOR_DATABASE_URL (ou DATABASE_URL) com a URL do PostgreSQL antes de migrar."
        )
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
