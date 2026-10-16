"""Criação do engine e das sessões. Nada é conectado até a primeira consulta."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


def create_db_engine(url: str) -> Engine:
    if url.startswith("sqlite"):
        # Usado só nos testes. Em memória, a conexão precisa ser única e compartilhada.
        return create_engine(
            url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    # Pool pequeno: em serverless (Vercel) cada instância abre poucas conexões; use a
    # connection string "pooled" do provedor. pool_pre_ping descarta conexões que o
    # provedor derrubou por ociosidade.
    return create_engine(
        url,
        pool_size=1,
        max_overflow=1,
        pool_pre_ping=True,
        pool_recycle=300,
    )


class Database:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._factory = sessionmaker(engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._factory() as session:
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise

    def ping(self) -> bool:
        from sqlalchemy import text

        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False
