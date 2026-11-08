from fastapi import APIRouter


def get_health_router() -> APIRouter:
    from .schemas import HealthResponse

    router = APIRouter()

    @router.get(
        "",
        tags=["healthcheck"],
        summary="Healthcheck",
        description="Проверка жизни сервиса.",
        status_code=200,
    )
    async def health() -> HealthResponse:
        return HealthResponse()

    return router
