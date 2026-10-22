import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.experiments import router as experiments_router
from app.api.mg1 import distributions_router, router as mg1_router
from app.api.mm1 import router as mm1_router
from app.api.phase10 import erlangb_router, mgc_router
from app.api.queues import mm1k_router, mmc_router, mmck_router
from app.api.finite_population import router as finite_population_router
from app.api.realdata import router as realdata_router
from app.api.realdata_extra import router as realdata_extra_router
from app.api.records import router as records_router
from app.api.sizing import router as sizing_router
from app.persistence.config import PersistenceLimits, database_url_from_env
from app.persistence.database import Database, create_db_engine

CORS_ENV_VAR = "QSIMULADOR_CORS_ORIGINS"


def parse_origins(value: str | None) -> list[str]:
    """Lê uma lista de origens separadas por vírgula (ex.: "https://meusite.com,http://localhost:5173")."""
    if not value:
        return []
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def build_database_from_env() -> Database | None:
    """Cria o acesso ao banco se houver URL configurada; senão, a persistência fica desativada."""
    url = database_url_from_env()
    return Database(create_db_engine(url)) if url else None


def create_app(
    cors_origins: list[str] | None = None,
    database: Database | None = None,
    limits: PersistenceLimits | None = None,
) -> FastAPI:
    """Monta a aplicação. O CORS só é ativado se houver origens permitidas.

    O banco é opcional (RNF-18): sem `database` e sem URL nas variáveis de ambiente, o
    núcleo funciona normalmente e as rotas de histórico respondem 503.

    Em desenvolvimento não precisa: o proxy do Vite faz as chamadas à API pela mesma origem.
    """
    application = FastAPI(
        title="QSimulador API",
        version="0.1.0",
        description="Modelagem, simulação e análise de sistemas de filas.",
    )
    if cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Content-Type", "X-Client-Id"],
            allow_credentials=False,
        )

    application.state.database = database if database is not None else build_database_from_env()
    application.state.limits = limits or PersistenceLimits.from_env()

    register_exception_handlers(application)
    application.include_router(mm1_router)
    application.include_router(mg1_router)
    application.include_router(distributions_router)
    application.include_router(mmc_router)
    application.include_router(mm1k_router)
    application.include_router(mmck_router)
    application.include_router(erlangb_router)
    application.include_router(mgc_router)
    application.include_router(experiments_router)
    application.include_router(sizing_router)
    application.include_router(realdata_router)
    application.include_router(realdata_extra_router)
    application.include_router(finite_population_router)
    application.include_router(records_router)

    @application.get("/api/health", tags=["infra"])
    def health(request: Request) -> dict[str, str]:
        """Verifica se a API está no ar e se a persistência está configurada."""
        enabled = request.app.state.database is not None
        return {"status": "ok", "persistence": "enabled" if enabled else "disabled"}

    return application


app = create_app(parse_origins(os.getenv(CORS_ENV_VAR)))
