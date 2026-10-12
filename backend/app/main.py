import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.mm1 import router as mm1_router
from app.api.queues import mm1k_router, mmc_router, mmck_router

# --- NOVOS IMPORTS DA FASE 6 ---
from app.api.schemas import SweepRequest, SweepResponse
from app.experiments.sweep import run_analytical_sweep
# -------------------------------

CORS_ENV_VAR = "QSIMULADOR_CORS_ORIGINS"


def parse_origins(value: str | None) -> list[str]:
    """Lê uma lista de origens separadas por vírgula (ex.: "https://meusite.com,http://localhost:5173")."""
    if not value:
        return []
    return [origin.strip() for origin in value.split(",") if origin.strip()]


def create_app(cors_origins: list[str] | None = None) -> FastAPI:
    """Monta a aplicação. O CORS só é ativado se houver origens permitidas.

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
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type"],
            allow_credentials=False,
        )

    register_exception_handlers(application)
    application.include_router(mm1_router)
    application.include_router(mmc_router)
    application.include_router(mm1k_router)
    application.include_router(mmck_router)

    @application.get("/api/health", tags=["infra"])
    def health() -> dict[str, str]:
        """Verifica se a API está no ar."""
        return {"status": "ok"}

    # --- NOVA ROTA DA FASE 6 ---
    @application.post("/api/experiments/sweep", response_model=SweepResponse, tags=["experiments"])
    def run_experiment_sweep(request: SweepRequest):
        """Fase 6: Varredura de parâmetros analíticos."""
        points = run_analytical_sweep(request)
        return SweepResponse(
            model_type=request.model_type,
            sweep_variable=request.sweep_variable,
            points=points
        )
    # ---------------------------

    return application


app = create_app(parse_origins(os.getenv(CORS_ENV_VAR)))