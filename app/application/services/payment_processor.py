import asyncio
import random
from datetime import datetime, timezone

import structlog

from app.application.ports.unit_of_work import AbstractUnitOfWork
from app.domain.payment import Payment, PaymentStatus
from app.domain.events import PaymentCreatedEvent
from app.infrastructure.webhooks.client import WebhookClient, WebhookDeliveryError

logger = structlog.get_logger()


class PaymentProcessingError(Exception):
    """Ошибка при обработке платежа (шлюз вернул ошибку)."""

    pass


class PaymentProcessor:
    """Сервис обработки платежа (эмуляция + обновление + webhook)."""

    def __init__(self, uow: AbstractUnitOfWork, webhook_client: WebhookClient):
        self.uow = uow
        self.webhook_client = webhook_client

    async def process(self, event: PaymentCreatedEvent) -> None:
        """
        Обрабатывает событие создания платежа.
        """
        async with self.uow:
            payment = await self.uow.payments.get_by_id(event.payment_id)

            if not payment:
                logger.error(
                    "Payment not found for event", payment_id=str(event.payment_id)
                )
                raise ValueError(f"Payment {event.payment_id} not found")

            # Идемпотентность consumer'а: если уже обработан - просто ack'аем
            if payment.status != PaymentStatus.PENDING:
                logger.info(
                    "Payment already processed (idempotent redelivery)",
                    payment_id=str(payment.id),
                    current_status=payment.status,
                )
                return

            # 1. Эмуляция платёжного шлюза
            try:
                success = await self._simulate_payment_gateway()
            except Exception as e:
                logger.error("Payment gateway simulation failed", error=str(e))
                raise

            # 2. Обновляем статус
            if success:
                payment.succeed()
                logger.info("Payment succeeded", payment_id=str(payment.id))
            else:
                payment.fail()
                logger.warning("Payment failed", payment_id=str(payment.id))

            await self.uow.payments.update(payment)
            await self.uow.commit()

        # 3. Отправляем webhook (ВНЕ транзакции БД!)
        webhook_payload = {
            "event": "payment.completed",
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": str(payment.amount),
            "currency": payment.currency,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        try:
            await self.webhook_client.send_webhook(
                url=payment.webhook_url,
                payload=webhook_payload,
                correlation_id=str(event.event_id),
            )
        except WebhookDeliveryError as e:
            logger.error(
                "Webhook delivery failed after all retries",
                payment_id=str(payment.id),
                webhook_url=payment.webhook_url,
                error=str(e),
            )
            raise

    async def _simulate_payment_gateway(self) -> bool:
        """
        Эмулирует работу платёжного шлюза.

        - Задержка 2-5 секунд
        - 90% успех, 10% ошибка
        """
        delay = random.uniform(2.0, 5.0)
        await asyncio.sleep(delay)

        # 90% success, 10% fail
        return random.random() < 0.9
