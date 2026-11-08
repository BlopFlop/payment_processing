from httpx import AsyncClient, Response

import pytest


HEALTH_URL = "/health"
OPENAPI_URL = "/openapi.json"


async def test_health(anon_client: AsyncClient) -> None:
    response: Response = await anon_client.get(HEALTH_URL)
    assert response.status_code == 200, (
        f"Роутер health должен вернуть код 200 без API ключа, а вернул {response.status_code}"
    )
    assert response.json() == {"status": "ok"}, f"Тело health должно быть {{'status': 'ok'}}, а не {response.json()}"


@pytest.mark.parametrize("path", ["/v1/payments", "/v1/payments/{payment_id}", "/health"])
async def test_openapi(anon_client: AsyncClient, path: str) -> None:
    response: Response = await anon_client.get(OPENAPI_URL)
    assert response.status_code == 200, f"OpenAPI должен отдаваться с кодом 200, а не {response.status_code}"
    paths = response.json()["paths"]
    assert f"/api{path}" in paths, f"В OpenAPI должен быть описан путь /api{path}"
