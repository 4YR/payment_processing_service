# tests/unit/test_domain.py
import uuid
from decimal import Decimal
from app.domain.payment import Payment, PaymentStatus
from app.domain.events import PaymentCreatedEvent


def test_payment_succeed():
    payment = Payment(
        amount=Decimal("100.00"),
        currency="RUB",
        idempotency_key="test",
        webhook_url="http://test",
    )
    assert payment.status == PaymentStatus.PENDING

    payment.succeed()

    assert payment.status == PaymentStatus.SUCCEEDED
    assert payment.updated_at >= payment.created_at


def test_payment_fail():
    payment = Payment(
        amount=Decimal("50.00"),
        currency="USD",
        idempotency_key="test",
        webhook_url="http://test",
    )
    payment.fail()
    assert payment.status == PaymentStatus.FAILED


def test_event_creation():
    event = PaymentCreatedEvent(
        payment_id=uuid.uuid4(),
        amount=Decimal("100.00"),
        currency="RUB",
        webhook_url="http://test",
    )

    assert event.event_id is not None
    assert event.created_at is not None
    assert event.event_type == "payment.created"
