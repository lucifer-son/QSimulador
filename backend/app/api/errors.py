"""Conversão de erros em respostas HTTP padronizadas (422).

Todo 422 tem o formato {"code", "message", "fields"?}, seja o erro de tipo/forma
(detectado pelo Pydantic) ou de regra de domínio (ex.: sistema instável). Os erros de
regra trazem em `fields` o campo a que se referem, quando existe um.
"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.domain.validation.errors import (
    InsufficientSampleError,
    InvalidDatasetError,
    QueueValidationError,
    UnstableSystemError,
)


class ApiError(Exception):
    """Erro de API com status, código e mensagem no formato padrão {"code", "message"}."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def _domain_code(exc: QueueValidationError) -> str:
    if isinstance(exc, UnstableSystemError):
        return "unstable_system"
    if isinstance(exc, InsufficientSampleError):
        return "insufficient_sample"
    if isinstance(exc, InvalidDatasetError):
        return "invalid_dataset"
    return "invalid_parameter"


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status_code, content={"code": exc.code, "message": exc.message}
        )

    @app.exception_handler(QueueValidationError)
    async def handle_domain_error(request: Request, exc: QueueValidationError):
        content: dict = {"code": _domain_code(exc), "message": str(exc)}
        if exc.field:
            content["fields"] = [{"field": exc.field, "message": str(exc)}]
        return JSONResponse(status_code=422, content=content)

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
