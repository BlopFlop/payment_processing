from dataclasses import asdict, dataclass, fields
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from pydantic_core import to_jsonable_python

from app.models import Event, PaymentStatus


if TYPE_CHECKING:
    from _typeshed import DataclassInstance


class Unset(Enum):
    UNSET = "UNSET"


UNSET = Unset.UNSET


class DtoDB:
    @classmethod
    def from_orm[D: "DataclassInstance"](cls: type[D], model: object) -> D:
        return cls(**{field.name: getattr(model, field.name) for field in fields(cls)})


class DtoJsonDictMixin:
    def as_json_dict(self: "DataclassInstance") -> dict[str, Any]:
        result: dict[str, Any] = to_jsonable_python(asdict(self))
        return result


class UpdateDtoMixin:
    def as_dict(self: "DataclassInstance") -> dict[str, Any]:
        return {
            field.name: getattr(self, field.name) for field in fields(self) if getattr(self, field.name) is not UNSET
        }

    def as_json_dict(self: "DataclassInstance") -> dict[str, Any]:
        result: dict[str, Any] = to_jsonable_python(UpdateDtoMixin.as_dict(self))
        return result


@dataclass(slots=True)
class PaymentDtoCreate(DtoJsonDictMixin):
    amount: Decimal
    currency: str
    idempotency_key: str
    metadata_: dict[str, Any]
    description: str | None = None
    webhook_url: str | None = None
    status: PaymentStatus = PaymentStatus.PENDING


@dataclass(slots=True)
class PaymentDtoUpdate(UpdateDtoMixin):
    webhook_url: str | None | Unset = UNSET
    status: PaymentStatus | Unset = UNSET
    status_updated: datetime | Unset = UNSET
    processed_at: datetime | Unset = UNSET


@dataclass(frozen=True, slots=True)
class PaymentDtoDB(DtoJsonDictMixin, DtoDB):
    id: UUID
    idempotency_key: str
    status: PaymentStatus
    amount: Decimal
    currency: str
    description: str | None
    metadata_: dict[str, Any]
    webhook_url: str | None
    created_at: datetime
    status_updated: datetime
    processed_at: datetime | None


@dataclass(slots=True)
class OutboxDtoCreate(DtoJsonDictMixin):
    event_type: Event
    payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class OutboxDtoDB(DtoJsonDictMixin, DtoDB):
    id: int
    event_type: Event
    payload: dict[str, Any]
    is_processed: bool
    created_at: datetime
    processed_at: datetime | None


@dataclass(frozen=True, slots=True)
class OutboxDtoUpdate(UpdateDtoMixin):
    payload: dict[str, Any] | Unset = UNSET
    is_processed: bool | Unset = UNSET
    processed_at: datetime | None | Unset = UNSET


class PaymentFingerprint(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)

    amount: Decimal
    currency: str
    description: str | None
    metadata_: dict[str, Any]
    webhook_url: str | None
