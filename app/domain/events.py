import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pydantic import BaseModel


class PaymentCreatedEvent(BaseModel):
    """Событие создания платежа для публикации в MQ."""

    event_id: uuid.UUID = uuid.uuid4()
    event_type: str = "payment.created"
    payment_id: uuid.UUID
    amount: Decimal
    currency: str
    webhook_url: str
    created_at: datetime = datetime.now(timezone.utc())
