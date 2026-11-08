from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from .schemas import IdempotencyConflictError, PaymentNotFoundError
from app.services.exceptions import IdempotencyConflict, PaymentNotFound


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(PaymentNotFound)
    async def _not_found(_: Request, exc: PaymentNotFound) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content=PaymentNotFoundError(detail=str(exc)).model_dump(),
        )

    @app.exception_handler(IdempotencyConflict)
    async def _conflict(_: Request, exc: IdempotencyConflict) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content=IdempotencyConflictError(detail=str(exc)).model_dump(),
        )
