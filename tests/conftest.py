from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer

from app.infrastructure.db.models import Base
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.presentation.api.deps import get_uow
from app.main import app as fastapi_app


@pytest.fixture(scope="session")
def postgres_container():
    """Поднимает реальный PostgreSQL в Docker на время тестов."""
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest_asyncio.fixture(scope="session")
async def async_engine(postgres_container):
    """Создаёт async engine для тестовой БД."""
    url = (
        f"postgresql+asyncpg://{postgres_container.username}:"
        f"{postgres_container.password}@"
        f"{postgres_container.get_container_host_ip()}:"
        f"{postgres_container.get_exposed_port(5432)}/"
        f"{postgres_container.dbname}"
    )

    engine = create_async_engine(url, echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Создаёт новую сессию для каждого теста."""
    session_factory = async_sessionmaker(async_engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(async_engine) -> AsyncGenerator[AsyncClient, None]:
    """Async HTTP клиент для тестирования FastAPI с подменой БД."""

    test_session_factory = async_sessionmaker(async_engine, expire_on_commit=False)

    class TestSQLAlchemyUnitOfWork(SQLAlchemyUnitOfWork):
        def __init__(self):
            self.session_factory = test_session_factory

    async def override_get_uow():
        uow = TestSQLAlchemyUnitOfWork()
        async with uow:
            yield uow

    fastapi_app.dependency_overrides[get_uow] = override_get_uow

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    fastapi_app.dependency_overrides.clear()
