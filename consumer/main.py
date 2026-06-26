import asyncio
import logging
import signal
import sys
from typing import Any

import structlog
from faststream import FastStream, Context
from faststream.rabbit import RabbitBroker, RabbitExchange, RabbitQueue, ExchangeType

from app.config import settings
from app.infrastructure.db.unit_of_work import SQLAlchemyUnitOfWork
from app.infrastructure.webhooks.client import WebhookClient
from app.application.services.payment_processor import PaymentProcessor
from app.domain.events import PaymentCreatedEvent


def setup_logging() -> None:
    """Настройка structlog для consumer'а."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.dev.set_exc_info,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelName(settings.log_level)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )

logger = structlog.get_logger()    


# Настраиваем broker и приложение FastStream
broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)

# Объявляем exchange и queue (должны совпадать с теми, что в Outbox Worker)
payments_exchange = RabbitExchange(
    name="payments",
    type=ExchangeType.TOPIC,
    durable=True,
) 

payments_new_queue = RabbitQueue(
    name="payments.new",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "",
        "x-dead-letter-routing-key": "payments.new.dlq",
    },
)

# Webhook client - один на весь consumer (connection pooling)
webhook_client = WebhookClient()


@broker.subscriber(
    queue=payments_new_queue,
    exchange=payments_exchange,
)
async def process_payment_event(
    event_data: dict,
    message: Any = Context("message"),
) -> None:
    """
    Обрабатывает событие создания платежа из очереди payments.new.
    
    Если обработка упадет после всех retry - FastStream nack'ает сообщение,
    и RabbitMQ отправит его в payments.new.dlq.
    """
    # Получаем correlation ID из заголовков сообщения
    correlation_id = None
    if hasattr(message, "headers") and message.headers:
        correlation_id = message.headers.get("correlation_id")

    structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

    try:
        event = PaymentCreatedEvent(**event_data)

        logger.info(
            "Received payment event",
            event_id=str(event.event_id),
            payment_id=str(event.payment_id),
        )

        uow = SQLAlchemyUnitOfWork()

        processor = PaymentProcessor(uow, webhook_client)
        await processor.process(event)

        logger.info(
            "Payment event processed successfully",
            event_id=str(event.event_id),
            payment_id=str(event.payment_id),
        )
    except Exception as e:
        logger.error(
            "Failed to process payment event",
            error=str(e),
            exc_info=True,
        )
        raise
    finally:
        structlog.contextvars.clear_contextvars()


@app.after_shutdown
async def cleanup() -> None:
    """Очистка ресурсов после остановки consumer'а."""
    await webhook_client.close()        
    logger.info("Consumer resources cleaned")

shutdown_event = asyncio.Event()


def handle_shutdown(signum: int, frame: Any) -> None:
    logger.info("Received shutdown signal", signal=signum)
    shutdown_event.set()


async def main() -> None:
    """Главная функция consumer'а."""
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)
    
    logger.info("Starting payment consumer...")
    await app.run()


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"CRITICAL CONSUMER ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)    