# Payment Processing Service

Асинхронный микросервис для процессинга платежей. Принимает запросы на оплату, обрабатывает их через эмуляцию платёжного шлюза и уведомляет клиента о результате через webhook.

## Архитектура

```
Client → POST /api/v1/payments (Idempotency-Key, X-API-Key)
                      ↓
              FastAPI (Presentation)
                      ↓
           Application Service (UoW)
                      ↓
     ┌──────────────────────────────────┐
     │  Атомарная транзакция:           │
     │  1. Сохраняем Payment (pending)  │
     │  2. Сохраняем OutboxMessage      │
     └──────────────────────────────────┘
                      ↓
          Outbox Worker (polling)
                      ↓
      RabbitMQ → payments.new queue
                      ↓
          Consumer (FastStream)
                      ↓
     ┌──────────────────────────────────┐
     │  1. Эмуляция шлюза (2-5 сек)     │
     │  2. Обновление статуса в БД      │
     │  3. Webhook на указанный URL     │
     └──────────────────────────────────┘
```

### Ключевые решения

- **Outbox Pattern** — гарантирует доставку событий в RabbitMQ
- **Dead Letter Queue** — необработанные сообщения попадают в `payments.new.dlq`
- **Идемпотентность** — защита от дублей через `Idempotency-Key`
- **Unit of Work** — автоматический rollback при ошибках

## Стек технологий

| Компонент | Технология |
|---|---|
| API | FastAPI + Pydantic v2 |
| База данных | PostgreSQL (SQLAlchemy 2.0 async) |
| Брокер | RabbitMQ (FastStream + aio-pika) |
| Миграции | Alembic |
| Логирование | structlog |
| Тесты | pytest, testcontainers |
| Контейнеризация | Docker + docker-compose |

## Быстрый запуск

```bash
git clone <repo-url>
cd payment-processing-service
docker compose up --build
```

После запуска будут доступны:

| Сервис | URL |
|---|---|
| API | http://localhost:8000 |
| Swagger UI | http://localhost:8000/api/docs |
| ReDoc | http://localhost:8000/api/redoc |
| RabbitMQ Management | http://localhost:15672 (guest/guest) |


## Примеры запросов

### Создание платежа

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key" \
  -H "Idempotency-Key: unique-key-123" \
  -d '{
    "amount": 1500.50,
    "currency": "RUB",
    "description": "Оплата заказа №123",
    "webhook_url": "https://example.com/webhook",
    "metadata": {
      "order_id": "order-456",
      "customer_id": "cust-789"
    }
  }'
```

**Ответ (202 Accepted):**
```json
{
  "id": "3f2c1a5b-8d4e-4f7a-9c1b-2d3e4f5a6b7c",
  "amount": "1500.50",
  "currency": "RUB",
  "description": "Оплата заказа №123",
  "metadata": {
    "order_id": "order-456",
    "customer_id": "cust-789"
  },
  "status": "pending",
  "webhook_url": "https://example.com/webhook",
  "created_at": "2026-06-27T10:30:00+00:00",
  "updated_at": "2026-06-27T10:30:00+00:00"
}
```

### Получение платежа

```bash
curl http://localhost:8000/api/v1/payments/3f2c1a5b-8d4e-4f7a-9c1b-2d3e4f5a6b7c \
  -H "X-API-Key: test-api-key"
```

**Ответ (200 OK):**
```json
{
  "id": "3f2c1a5b-8d4e-4f7a-9c1b-2d3e4f5a6b7c",
  "amount": "1500.50",
  "currency": "RUB",
  "status": "succeeded",
  "webhook_url": "https://example.com/webhook",
  "created_at": "2026-06-27T10:30:00+00:00",
  "updated_at": "2026-06-27T10:35:00+00:00"
}
```

### Идемпотентность

Повторный POST с тем же `Idempotency-Key` вернёт существующий платеж:

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: test-api-key" \
  -H "Idempotency-Key: unique-key-123" \
  -d '{
    "amount": 1500.50,
    "currency": "RUB",
    "webhook_url": "https://example.com/webhook"
  }'
```

## Webhook уведомление

После обработки платежа Consumer отправляет POST на `webhook_url`:

```json
{
  "event": "payment.completed",
  "payment_id": "3f2c1a5b-...",
  "status": "succeeded",
  "amount": "1500.50",
  "currency": "RUB",
  "processed_at": "2026-06-27T10:35:00.123456+00:00"
}
```

При ошибках доставки — 3 попытки с экспоненциальной задержкой. После исчерпания — сообщение в DLQ.

## Компоненты системы

### API (FastAPI)
- Эндпоинты создания и получения платежа
- Валидация входных данных (Pydantic v2)
- Аутентификация через X-API-Key
- Swagger-документация

### Consumer
Слушает очередь `payments.new` и:
1. Эмулирует обработку платёжным шлюзом (2-5 сек, 90% успех / 10% ошибка)
2. Обновляет статус платежа в БД
3. Отправляет webhook-уведомление
4. При ошибках — 3 ретрая, затем DLQ

### Outbox Worker
- Периодически опрашивает таблицу `outbox_messages`
- Публикует необработанные события в RabbitMQ
- Использует `FOR UPDATE SKIP LOCKED` для конкурентной работы

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5432/payments` | Подключение к PostgreSQL |
| `RABBITMQ_URL` | `amqp://guest:guest@localhost:5672/` | Подключение к RabbitMQ |
| `API_KEY` | `test-api-key` | Ключ для X-API-Key |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `OUTBOX_POLL_INTERVAL_SECONDS` | `1.0` | Интервал опроса outbox (сек) |
| `OUTBOX_BATCH_SIZE` | `100` | Размер батча outbox |
| `WEBHOOK_TIMEOUT_SECONDS` | `10.0` | Таймаут отправки webhook (сек) |
| `WEBHOOK_MAX_RETRIES` | `3` | Попыток отправки webhook |

## Разработка

### Локальный запуск без Docker

```bash
# 1. Установить зависимости
uv sync

# 2. Создать .env файл
cp .env.example .env

# 3. Запустить PostgreSQL и RabbitMQ
docker compose up postgres rabbitmq -d

# 4. Применить миграции
uv run alembic upgrade head

# 5. Запустить API
uv run uvicorn app.main:app --reload

# 6. В отдельном терминале — Consumer
uv run python -m consumer.main

# 7. В отдельном терминале — Outbox Worker
uv run python -m outbox_worker.worker
```

### Запуск тестов

```bash
uv run pytest -v
```



## Структура проекта

```
├── app/                          # FastAPI приложение
│   ├── main.py                   # Точка входа
│   ├── config.py                 # Конфигурация
│   ├── domain/                   # Доменный слой
│   │   ├── payment.py            # Payment + PaymentStatus
│   │   └── events.py             # PaymentCreatedEvent
│   ├── application/              # Прикладной слой
│   │   ├── dtos.py               # Pydantic схемы
│   │   ├── ports/                # Абстракции
│   │   │   ├── repositories.py   # AbstractPaymentRepository
│   │   │   └── unit_of_work.py   # AbstractUnitOfWork
│   │   └── services/             # Сервисы
│   │       ├── payment_service.py
│   │       └── payment_processor.py
│   ├── infrastructure/           # Инфраструктура
│   │   ├── db/                   # PostgreSQL (SQLAlchemy)
│   │   ├── mq/                   # RabbitMQ (FastStream)
│   │   └── webhooks/             # HTTP клиент (httpx)
│   └── presentation/             # Слой представления
│       ├── api/v1/payments.py    # Эндпоинты
│       └── middleware/           # Middleware
├── consumer/main.py              # Consumer
├── outbox_worker/worker.py       # Outbox Worker
├── migrations/                   # Alembic миграции
├── tests/                        # Тесты
├── docker-compose.yml            # Docker Compose
└── pyproject.toml                # Зависимости
```

