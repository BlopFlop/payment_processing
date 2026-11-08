from fastapi import Depends

from app.api.deps import get_outbox_repository, get_payment_repository
from app.repository import OutboxRepository, PaymentRepository
from app.services import PaymentService


def build_payment_service(
    payment_repository: PaymentRepository = Depends(get_payment_repository),
    outbox_repository: OutboxRepository = Depends(get_outbox_repository),
) -> PaymentService:
    service = PaymentService()
    service.payment_repo = payment_repository
    service.outbox_repo = outbox_repository
    return service
