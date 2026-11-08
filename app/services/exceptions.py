import uuid


class PaymentError(Exception):
    pass


class PaymentNotFound(PaymentError):
    def __init__(self, payment_id: uuid.UUID) -> None:
        super().__init__(f"Payment {payment_id} not found")
        self.payment_id = payment_id


class IdempotencyConflict(PaymentError):
    def __init__(self, idem_key: str) -> None:
        super().__init__(f"Idempotency-Key {idem_key!r} was already used with a different request body")
        self.idem_key = idem_key
