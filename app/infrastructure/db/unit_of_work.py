from sqlalchemy.ext.asyncio import AsyncSession
from app.application.ports.unit_of_work import AbstractUnitOfWork
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.repositories import (
    SQLAlchemyPaymentRepository,
    SQLAlchemyOutboxRepository,
)


class SQLAlchemyUnitOfWork(AbstractUnitOfWork):
    def __init__(self):
        self.session_factory = async_session_factory

    async def __aenter__(self) -> "SQLAlchemyUnitOfWork":
        self.session: AsyncSession = self.session_factory()
        self.payments = SQLAlchemyPaymentRepository(self.session)
        self.outbox = SQLAlchemyOutboxRepository(self.session)
        return await super().__aenter__()

    async def __aexit__(self, *args):
        await super().__aexit__(*args)
        await self.session.close()

    async def commit(self) -> None:
        await self.session.commit()

    async def rollback(self):
        await self.session.rollback()
