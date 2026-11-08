from fastapi import APIRouter


def get_router() -> APIRouter:
    from .payments import get_payments_router

    router = APIRouter(tags=["v1"])
    router.include_router(get_payments_router(), prefix="/payments")

    return router
