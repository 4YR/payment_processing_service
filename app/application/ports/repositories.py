import uuid
from abc import ABC, abstractmethod
from app.domain.payment import Payment
from app.domain.events import PaymentCreatedEvent


class AbstractPaymentRepository(ABC):
    @abstractmethod
    async def add(self, payment: Payment) -> None: ...

    @abstractmethod
    async def get_by_id(self, payment_id: uuid.UUID) -> Payment | None: ...

    @abstractmethod
    async def get_by_idempotency_key(self, key: str) -> Payment | None: ...


class AbstractOutboxRepository(ABC):
    @abstractmethod
    async def add(self, event: PaymentCreatedEvent) -> None: ...
