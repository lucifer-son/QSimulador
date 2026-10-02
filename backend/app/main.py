from fastapi import FastAPI

from app.api.errors import register_exception_handlers
from app.api.mm1 import router as mm1_router

app = FastAPI(
    title="QueueLab API",
    version="0.1.0",
    description="Modelagem, simulação e análise de sistemas de filas.",
)

register_exception_handlers(app)
app.include_router(mm1_router)


@app.get("/api/health", tags=["infra"])
def health() -> dict[str, str]:
    """Verifica se a API está no ar."""
    return {"status": "ok"}
