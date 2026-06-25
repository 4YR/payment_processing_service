import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from enum import Enum

from pydantic import BaseModel, Field


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Payment(BaseModel):
    """Доменная сущность Платежа."""
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4)
    amount: Decimal
    currency: str
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    status: PaymentStatus = PaymentStatus.PENDING
    idempotency_key: str
    webhook_url: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    def succeed(self) -> None:
        self.status = PaymentStatus.SUCCEEDED
        self.updated_at = datetime.now(timezone.utc)

    def fail(self) -> None:
        self.status = PaymentStatus.FAILED
        self.updated_at = datetime.now(timezone.utc)
