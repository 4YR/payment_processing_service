from typing import AsyncGenerator
from fastapi import Depends, HTTPException, Security, status, Header
from fastapi.security import APIKeyHeader

from app.application.ports.unit_of_work import AbstractUnitOfWork
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def get_uow() -> AsyncGenerator[AbstractUnitOfWork, None]:
    """Dependency для получения UnitOfWork."""
    uow = SQLAlchemyUnitOfWork()
    try:
        yield uow
    finally:
        if hasattr(uow, "session"):
            await uow.session.close()


async def verify_api_key(api_key: str = Header(..., alias="X-API-Key")) -> None:
    """Dependency для проверки API ключа."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-API-Key header",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    return api_key
