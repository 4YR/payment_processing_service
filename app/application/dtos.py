import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any
from pydantic import BaseModel, Field, field_validator


class CreatePaymentRequest(BaseModel):
    """Схема запроса на создание платежа."""

    amount: Decimal = Field(..., gt=0, decimal_places=2)
    currency: str = Field(..., pattern=r"^[A-Z]{3}")
    description: str | None = Field(None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)
    webhook_url: str = Field(..., max_length=2048)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if v not in ["RUB", "USD", "EUR"]:
            raise ValueError("Currency must be RUB, USD, or EUR")
        return v


class PaymentResponse(BaseModel):
    """Схема ответа с информацией о платеже."""

    id: uuid.UUID
    amount: Decimal
    currency: str
    description: str | None
    metadata: dict[str, Any]
    status: str
    webhook_url: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ErrorResponse(BaseModel):
    """RFC 7807 Problem Details for error responses."""

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class IdempotencyError(BaseModel):
    """Ошибка при дублировании idempotency key."""

    existing_payment_id: uuid.UUID
    message: str = "Payment with this idempotency key already exists"
