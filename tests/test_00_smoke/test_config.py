from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

import pytest

from faststream import FastStream

from app.core.config import AppType, Settings


@pytest.mark.parametrize("app_type", list(AppType))
def test_settings(monkeypatch: pytest.MonkeyPatch, app_type: AppType) -> None:
    monkeypatch.setenv("APISERVICE_APP_TYPE", app_type.value)
    settings = Settings()

    assert settings.APP_TYPE == app_type, (
        f"Настройки должны загрузиться с типом {app_type=}, а загрузились с {settings.APP_TYPE=}"
    )
    assert settings.API_KEY.get_secret_value(), "API ключ должен быть задан"
    assert settings.broker.URL.get_secret_value().startswith("amqp://"), "URL брокера должен быть amqp://"


def _init_api() -> FastAPI:
    from app.workers import init_api

    return init_api()


def _init_producer() -> FastStream:
    from app.workers import init_producer

    return init_producer()


def _init_consumer() -> FastStream:
    from app.workers import init_consumer

    return init_consumer()


@pytest.mark.parametrize(
    "app_type, factory, expected_type",
    (
        (AppType.API, _init_api, FastAPI),
        (AppType.PRODUCER, _init_producer, FastStream),
        (AppType.CONSUMER, _init_consumer, FastStream),
    ),
)
def test_app_factory(
    monkeypatch: pytest.MonkeyPatch,
    app_type: AppType,
    factory: Callable[[], Any],
    expected_type: type,
) -> None:
    monkeypatch.setenv("APISERVICE_APP_TYPE", app_type.value)
    app = factory()

    assert isinstance(app, expected_type), (
        f"Фабрика {app_type} должна вернуть {expected_type.__name__}, а вернула {type(app).__name__}"
    )


@pytest.mark.parametrize(
    "app_type, factory",
    (
        (AppType.PRODUCER, _init_producer),
        (AppType.CONSUMER, _init_consumer),
    ),
)
def test_faststream_app_has_broker(
    monkeypatch: pytest.MonkeyPatch, app_type: AppType, factory: Callable[[], Any]
) -> None:
    monkeypatch.setenv("APISERVICE_APP_TYPE", app_type.value)
    app = factory()

    assert app.broker is not None, f"Приложение {app_type} должно быть создано с брокером, иначе оно не запустится"
