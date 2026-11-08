from uuid import UUID

from pydantic import BaseModel, ConfigDict


class PaymentCreatedEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    event_id: int | None = None
    payment_id: UUID
