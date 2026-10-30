import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

logger = logging.getLogger(__name__)


class ApiError(HTTPException):
    def __init__(self, status_code: int, code: str, detail: str) -> None:
        self.code = code
        super().__init__(
            status_code,
            detail,
            headers={"WWW-Authenticate": "Bearer"} if status_code == 401 else None,
        )


def register_error_handlers(api: FastAPI) -> None:
    @api.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        codes = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "VALIDATION_ERROR",
        }
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "code": getattr(exc, "code", codes.get(exc.status_code, "HTTP_ERROR")),
            },
            headers=exc.headers,
        )

    @api.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Không phản chiếu input có thể chứa token hoặc mật khẩu vào lỗi.
        return JSONResponse(
            status_code=422,
            content={"detail": "Invalid request data", "code": "VALIDATION_ERROR"},
        )

    @api.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception) -> JSONResponse:
        logger.error("Unhandled API error: %s", type(exc).__name__)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "code": "INTERNAL_SERVER_ERROR"},
        )
