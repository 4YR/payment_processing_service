from datetime import datetime, timezone
import uuid
from sqlalchemy import select, update
from app.domain.payment import Payment
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.events import PaymentCreatedEvent
from app.application.ports.repositories import (
    AbstractPaymentRepository,
    AbstractOutboxRepository,
)
from app.infrastructure.db.models import (
    PaymentModel,
    OutboxMessageModel,
)


class SQLAlchemyPaymentRepository(AbstractPaymentRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, payment: Payment) -> None:
        db_model = PaymentModel(
            id=payment.id,
            amount=payment.amount,
            currency=payment.currency,
            description=payment.description,
            metadata_=payment.metadata,
            status=payment.status,
            idempotency_key=payment.idempotency_key,
            webhook_url=payment.webhook_url,
        )
        self.session.add(db_model)

    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None:
        stmt = select(PaymentModel).where(PaymentModel.id == payment_id)
        result = await self.session.execute(stmt)
        db_model = result.scalar_one_or_none()
        return self._to_domain(db_model) if db_model else None

    async def get_by_idempotency_key(self, key: str) -> Payment | None:
        stmt = select(PaymentModel).where(PaymentModel.idempotency_key == key)
        result = await self.session.execute(stmt)
        db_model = result.scalar_one_or_none()
        return self._to_domain(db_model) if db_model else None

    def _to_domain(self, model: PaymentModel) -> Payment:
        return Payment(
            id=model.id,
            amount=model.amount,
            currency=model.currency,
            description=model.description,
            metadata=model.metadata_,
            status=model.status,
            idempotency_key=model.idempotency_key,
            webhook_url=model.webhook_url,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )


class SQLAlchemyOutboxRepository(AbstractOutboxRepository):
    def __init__(self, session: AsyncSession):
        self.session = session

    async def add(self, event: PaymentCreatedEvent) -> None:
        db_model = OutboxMessageModel(
            id=event.event_id,
            event_type=event.event_type,
            payload=event.model_dump(mode="json"),
        )
        self.session.add(db_model)

    async def get_unprocessed_batch(
        self,
        batch_size: int,
    ) -> list[OutboxMessageModel]:
        """
        Получает батч необработанных сообщений из outbox.

        Использует FOR UPDATE SKIP LOCKED для безопасного конкурентного чтения
        (несколько worker'ов не будут обрабатывать одно и то же сообщение).
        """
        stmt = (
            select(OutboxMessageModel)
            .where(OutboxMessageModel.processed_at.is_(None))
            .order_by(OutboxMessageModel.created_at)
            .limit(batch_size)
            .with_for_update(skip_locked=True)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_as_processed(
        self,
        message_ids: list[uuid.UUID],
    ) -> None:
        """Помечает сообщения как обработанные."""
        stmt = (
            update(OutboxMessageModel)
            .where(OutboxMessageModel.id.in_(message_ids))
            .values(processed_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)
