import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pydantic import BaseModel, Field


class PaymentCreatedEvent(BaseModel):
    """Событие создания платежа для публикации в MQ."""
    event_id: uuid.UUID = Field(default_factory=uuid.uuid4)
    event_type: str = "payment.created"
    payment_id: uuid.UUID
    amount: Decimal
    currency: str
    webhook_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
