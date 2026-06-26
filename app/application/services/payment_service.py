import uuid
from typing import Self
import structlog

from app.application.dtos import CreatePaymentRequest
from app.application.ports.unit_of_work import AbstractUnitOfWork
from app.domain.payment import Payment
from app.domain.events import PaymentCreatedEvent

logger = structlog.get_logger()


class PaymentService:
    """Сервис для работы с платежами (Application Layer)."""

    def __init__(self, uow: AbstractUnitOfWork):
        self.uow = uow

    async def create_payment(
        self,
        request: CreatePaymentRequest,
        idempotency_key: str,
    ) -> tuple[Payment, bool]:
        """
        Создает новый платеж.

        Returns:
            tuple[Payment, bool]: (платеж, был ли создан новый или возвращен существующий)

        Raises:
            ValueError: Если платеж с таким idempotency key уже существует в другом статусе
        """

        async with self.uow:
            # Проверяем идемпотентность
            existing_payment = await self.uow.payments.get_by_idempotency_key(
                idempotency_key
            )

            if existing_payment:
                logger.info(
                    "Idempotent request detected",
                    idempotency_key=idempotency_key,
                    payment_id=str(existing_payment.id),
                )
                return existing_payment, False

            # Создаем новый платеж
            payment = Payment(
                amount=request.amount,
                currency=request.currency,
                description=request.description,
                metadata=request.metadata,
                idempotency_key=idempotency_key,
                webhook_url=request.webhook_url,
            )

            # Сохраняем платеж
            await self.uow.payments.add(payment)

            # Создаем событие для Outbox
            event = PaymentCreatedEvent(
                payment_id=payment.id,
                amount=payment.amount,
                currency=payment.currency,
                webhook_url=payment.webhook_url,
            )
            await self.uow.outbox.add(event)

            # Коммитим транзакцию (атомарно сохраняем Payment + OutboxMessage)
            await self.uow.commit()

            logger.info(
                "Payment created successfully",
                payment_id=str(payment.id),
                amount=str(payment.amount),
                currency=payment.currency,
            )
            return payment, True

    async def get_payment(self, payment_id: uuid.UUID) -> Payment | None:
        """Получает платеж по ID."""
        async with self.uow:
            payment = await self.uow.payments.get_by_id(payment_id)
            return payment
