from abc import ABC, abstractmethod
from types import TracebackType
from typing import Self
from app.application.ports.repositories import (
    AbstractPaymentRepository,
    AbstractOutboxRepository,
)


class AbstractUnitOfWork(ABC):
    payments: AbstractPaymentRepository
    outbox: AbstractOutboxRepository

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        await self.rollback()

    @abstractmethod
    async def commit(self) -> None: ...

    @abstractmethod
    async def rollback(self) -> None: ...
