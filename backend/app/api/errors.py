"""Conversão de erros em respostas HTTP padronizadas (422).

Todo 422 tem o formato {"code", "message", "fields"?}, seja o erro de tipo/forma
(detectado pelo Pydantic) ou de regra de domínio (ex.: sistema instável).
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.validation.errors import (
    InsufficientSampleError,
    QueueValidationError,
    UnstableSystemError,
)


def _domain_code(exc: QueueValidationError) -> str:
    if isinstance(exc, UnstableSystemError):
        return "unstable_system"
    if isinstance(exc, InsufficientSampleError):
        return "insufficient_sample"
    return "invalid_parameter"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(QueueValidationError)
    async def handle_domain_error(request: Request, exc: QueueValidationError):
        return JSONResponse(
            status_code=422,
            content={"code": _domain_code(exc), "message": str(exc)},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_error(request: Request, exc: RequestValidationError):
        fields = [
            {
                "field": ".".join(str(part) for part in err["loc"][1:]),
                "message": err["msg"],
            }
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={
                "code": "invalid_request",
                "message": "A requisição contém campos ausentes ou inválidos.",
                "fields": fields,
            },
        )
