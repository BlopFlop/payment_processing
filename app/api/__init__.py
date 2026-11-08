from fastapi import APIRouter

from .handlers import register_exception_handlers
from .health import get_health_router
from .v1 import get_router as get_v1_router


def get_router() -> APIRouter:
    router = APIRouter()

    router.include_router(get_v1_router(), prefix="/v1")
    router.include_router(get_health_router(), prefix="/health")

    return router


__all__ = ("register_exception_handlers",)
