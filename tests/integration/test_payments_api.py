import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payment import PaymentStatus


@pytest.mark.asyncio
async def test_create_payment_success(client, async_engine):
    """Тест успешного создания платежа."""
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": "test-api-key",
            "Idempotency-Key": f"test-{uuid.uuid4()}",
        },
        json={
            "amount": 100.50,
            "currency": "RUB",
            "description": "Test payment",
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 202
    data = response.json()
    assert data["status"] == PaymentStatus.PENDING.value
    assert data["amount"] == "100.5"
    assert data["currency"] == "RUB"
    assert "id" in data

    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("SELECT COUNT(*) FROM payments WHERE id = :id"),
            {"id": data["id"]},
        )
        assert result.scalar() == 1


@pytest.mark.asyncio
async def test_create_payment_idempotency(client):
    """Тест идемпотентности: повторный запрос возвращает существующий платеж."""
    idempotency_key = f"idem-{uuid.uuid4()}"
    payload = {
        "amount": 100.50,
        "currency": "RUB",
        "webhook_url": "https://example.com/webhook",
    }
    headers = {
        "X-API-Key": "test-api-key",
        "Idempotency-Key": idempotency_key,
    }

    response1 = await client.post(
        "/api/v1/payments",
        headers=headers,
        json=payload,
    )
    assert response1.status_code == 202
    payment_id_1 = response1.json()["id"]

    response2 = await client.post(
        "/api/v1/payments",
        headers=headers,
        json=payload,
    )
    assert response2.status_code == 202
    payment_id_2 = response2.json()["id"]

    assert payment_id_1 == payment_id_2


@pytest.mark.asyncio
async def test_create_payment_creates_outbox_message(client, async_engine):
    """Тест Outbox Pattern: создание платежа создаёт запись в outbox_messages."""
    idempotency_key = f"outbox-{uuid.uuid4()}"

    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": "test-api-key",
            "Idempotency-Key": idempotency_key,
        },
        json={
            "amount": 500.00,
            "currency": "USD",
            "webhook_url": "https://example.com/webhook",
        },
    )

    assert response.status_code == 202
    payment_id = response.json()["id"]

    async with async_engine.connect() as conn:
        result = await conn.execute(
            text("""
                SELECT COUNT(*), event_type, payload
                FROM outbox_messages
                WHERE payload->>'payment_id' = :payment_id
                GROUP BY event_type, payload
            """),
            {"payment_id": payment_id},
        )
        row = result.first()
        assert row is not None
        assert row[0] == 1
        assert row[1] == "payment.created"


@pytest.mark.asyncio
async def test_create_payment_without_api_key(client):
    """Тест аутентификации: запрос без API ключа возвращает 401."""
    response = await client.post(
        "/api/v1/payments",
        headers={"Idempotency-Key": f"no-auth-{uuid.uuid4()}"},
        json={
            "amount": 100.00,
            "currency": "RUB",
            "webhook_url": "https://example.com/webhook",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_payment_invalid_api_key(client):
    """Тест аутентификации: неверный API ключ возвращает 401."""
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": "wrong-key",
            "Idempotency-Key": f"bad-auth-{uuid.uuid4()}",
        },
        json={
            "amount": 100.00,
            "currency": "RUB",
            "webhook_url": "https://example.com/webhook",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_payment_invalid_currency(client):
    """Тест валидации: неподдерживаемая валюта возвращает 422."""
    response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": "test-api-key",
            "Idempotency-Key": f"val-{uuid.uuid4()}",
        },
        json={
            "amount": 100.00,
            "currency": "BTC",
            "webhook_url": "https://example.com/webhook",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_payment_success(client):
    """Тест получения существующего платежа."""
    idempotency_key = f"get-{uuid.uuid4()}"
    create_response = await client.post(
        "/api/v1/payments",
        headers={
            "X-API-Key": "test-api-key",
            "Idempotency-Key": idempotency_key,
        },
        json={
            "amount": 250.00,
            "currency": "EUR",
            "webhook_url": "https://example.com/webhook",
        },
    )
    payment_id = create_response.json()["id"]

    response = await client.get(
        f"/api/v1/payments/{payment_id}",
        headers={"X-API-Key": "test-api-key"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == payment_id
    assert data["amount"] == "250.00"
    assert data["currency"] == "EUR"


@pytest.mark.asyncio
async def test_get_payment_not_found(client):
    """Тест получения несуществующего платежа возвращает 404."""
    fake_id = uuid.uuid4()
    response = await client.get(
        f"/api/v1/payments/{fake_id}",
        headers={"X-API-Key": "test-api-key"},
    )
    assert response.status_code == 404
