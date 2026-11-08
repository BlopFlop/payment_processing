from collections.abc import Mapping
from enum import StrEnum

from pydantic import AliasGenerator, Field, SecretStr
from sqlalchemy.engine.url import URL

from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        alias_generator=AliasGenerator(validation_alias=lambda field_name: f"POSTGRES_{field_name}"),
    )

    TYPE: str = "postgresql+asyncpg"
    USER: str
    PASSWORD: str
    HOST: str
    PORT: int = 5432
    DB: str
    QUERY: Mapping[str, str] = {}

    POOL_PRE_PING: bool = True
    EXPIRE_ON_COMMIT: bool = False
    AUTOCOMMIT: bool = False
    AUTOFLUSH: bool = False
    POOL_RECYCLE: int = 3600
    POOL_SIZE: int = 5
    MAX_OVERFLOW: int = 10

    def build_url(self) -> URL:
        return URL.create(
            drivername=self.TYPE,
            username=self.USER,
            password=self.PASSWORD,
            host=self.HOST,
            port=self.PORT,
            database=self.DB,
            query=self.QUERY,
        )

    def build_dsn(self) -> str:
        return self.build_url().render_as_string(hide_password=False)


class BrokerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        alias_generator=AliasGenerator(validation_alias=lambda field_name: f"BROKERSERVICE_{field_name}"),
    )

    URL: SecretStr
    CONSUMER_PREFETCH: int = 5

    OUTBOX_APP_NAME: str = "Payment Outbox producer"
    OUTBOX_POLL_INTERVAL: float = 1.0
    OUTBOX_BATCH_SIZE: int = 100

    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_BASE_DELAY: float = 1.0

    WEBHOOK_TIMEOUT: int = 10


class AppType(StrEnum):
    API = "api"
    CONSUMER = "consumer"
    PRODUCER = "producer"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        alias_generator=AliasGenerator(validation_alias=lambda field_name: f"APISERVICE_{field_name}"),
    )

    broker: BrokerSettings = Field(default_factory=BrokerSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)

    APP_TYPE: AppType

    API_KEY: SecretStr
    NAME: str = "payment"
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    METRICS_PORT: int = 8001

    LOG_LEVEL: str = "INFO"

    @property
    def LOG_FILE(self) -> str:
        return f"logs/{self.APP_TYPE}.log"
