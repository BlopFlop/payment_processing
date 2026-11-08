from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel

from app.models import PaymentStatus


class WebhookPayload(BaseModel):
    event: str
    payment_id: UUID
    status: PaymentStatus
    amount: Decimal
    currency: str
    metadata: dict[str, Any]
    processed_at: datetime | None
