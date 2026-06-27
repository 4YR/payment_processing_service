import uuid
from abc import ABC, abstractmethod
from app.domain.payment import Payment
from app.domain.events import PaymentCreatedEvent
from app.infrastructure.db.models import OutboxMessageModel


class AbstractPaymentRepository(ABC):
    @abstractmethod
    async def add(self, payment: Payment) -> None: ...

    @abstractmethod
    async def update(self, payment: Payment) -> None: ...

    @abstractmethod
    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None: ...

    @abstractmethod
    async def get_by_idempotency_key(self, key: str) -> Payment | None: ...


class AbstractOutboxRepository(ABC):
    @abstractmethod
    async def add(self, event: PaymentCreatedEvent) -> None: ...

    @abstractmethod
    async def get_unprocessed_batch(
        self, batch_size: int
    ) -> list[OutboxMessageModel]: ...

    @abstractmethod
    async def mark_as_processed(self, message_ids: list[uuid.UUID]) -> None: ...
