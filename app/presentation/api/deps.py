from typing import AsyncGenerator
from fastapi import HTTPException, status, Header

from app.application.ports.unit_of_work import AbstractUnitOfWork
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.config import settings


async def get_uow() -> AsyncGenerator[AbstractUnitOfWork, None]:
    """Dependency для получения UnitOfWork."""
    uow = SQLAlchemyUnitOfWork()
    async with uow:
        yield uow


async def verify_api_key(
    x_api_key: str | None = Header(None, alias="X-API-Key")
) -> str:
    """Dependency для проверки API ключа."""
    if not x_api_key or x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )
    return x_api_key
