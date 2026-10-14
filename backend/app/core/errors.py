"""One error shape everywhere: {"error": {"code", "message", "details"}}."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFound(AppError):
    status_code = 404
    code = "not_found"


class Conflict(AppError):
    status_code = 409
    code = "conflict"


class VersionConflict(Conflict):
    code = "version_conflict"

    def __init__(self, what: str = "employee"):
        super().__init__(f"This {what} was changed by someone else. Reload to see the latest.")


class Forbidden(AppError):
    status_code = 403
    code = "forbidden"


class Unauthorized(AppError):
    status_code = 401
    code = "unauthorized"


class InvalidInput(AppError):
    status_code = 422
    code = "invalid"


class TooLarge(AppError):
    status_code = 413
    code = "too_large"


def error_body(code: str, message: str, details: dict[str, Any] | None = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _field_errors(exc: RequestValidationError) -> dict[str, str]:
    fields: dict[str, str] = {}
    for err in exc.errors():
        # loc looks like ("body", "amount") or ("query", "page")
        name = ".".join(str(part) for part in err["loc"][1:]) or str(err["loc"][0])
        fields.setdefault(name, err["msg"])
    return fields


def _respond(err: AppError, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(
        error_body(err.code, err.message, err.details),
        status_code=err.status_code,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_request: Request, exc: AppError):
        return _respond(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_request: Request, exc: RequestValidationError):
        return _respond(InvalidInput("Some fields are not valid.", {"fields": _field_errors(exc)}))

    @app.exception_handler(StaleDataError)
    async def _stale(_request: Request, _exc: StaleDataError):
        # Someone else saved the same employee between our read and our write.
        return _respond(VersionConflict())

    @app.exception_handler(IntegrityError)
    async def _integrity(_request: Request, _exc: IntegrityError):
        return _respond(Conflict("This change conflicts with existing data. Reload and try again."))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_request: Request, exc: StarletteHTTPException):
        err = AppError(str(exc.detail))
        err.status_code = exc.status_code
        err.code = {404: "not_found", 405: "method_not_allowed"}.get(exc.status_code, "error")
        return _respond(err, exc.headers)
