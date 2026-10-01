from fastapi import FastAPI

app = FastAPI(
    title="QueueLab API",
    version="0.1.0",
    description="Modelagem, simulação e análise de sistemas de filas.",
)


@app.get("/api/health", tags=["infra"])
def health() -> dict[str, str]:
    """Verifica se a API está no ar."""
    return {"status": "ok"}
