from fastapi import HTTPException

import pytest

from app.services.security import verify_api_key


@pytest.mark.parametrize(
    "key, status_code",
    (
        ("secret", None),
        (None, 401),
        ("", 401),
        ("wrong", 401),
        ("secret ", 401),
    ),
)
def test_verify_api_key(key: str | None, status_code: int | None) -> None:
    if status_code is None:
        verify_api_key(key, "secret")
        return

    with pytest.raises(HTTPException) as ex:
        verify_api_key(key, "secret")
    assert ex.value.status_code == status_code, f"Должен вернуться {status_code=}, а не {ex.value.status_code=}"
    assert ex.value.detail == "Invalid or missing API key", f"Неверное сообщение {ex.value.detail=}"
