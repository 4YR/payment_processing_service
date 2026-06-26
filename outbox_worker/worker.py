import asyncio
import logging
import signal
import sys
from typing import Any
import structlog

from app.config import settings
from app.infrastructure.db.session import async_session_factory
from app.infrastructure.db.repositories import SQLAlchemyOutboxRepository
from app.infrastructure.mq.faststream import (
    payment_created_publisher,
    broker,
    setup_rabbitmq_topology,
)
from app.domain.events import PaymentCreatedEvent


def setup_logging() -> None:
    """Настройка structlog для воркера."""
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

shutdown_event = asyncio.Event()


async def process_outbox_batch(batch_size: int) -> int:
    """Обрабатывает один батч outbox сообщений."""
    async with async_session_factory() as session:
        async with session.begin():
            outbox_repo = SQLAlchemyOutboxRepository(session)

            messages = await outbox_repo.get_unprocessed_batch(batch_size)

            if not messages:
                return 0

            logger.info(
                "Processing outbox batch",
                batch_size=len(messages),
                message_ids=[str(msg.id) for msg in messages],
            )

            for message in messages:
                try:
                    event = PaymentCreatedEvent(**message.payload)

                    await payment_created_publisher.publish(
                        event.model_dump(mode="json"),
                        correlation_id=str(event.event_id),
                    )

                    logger.info(
                        "Published event to RabbitMQ",
                        event_id=str(event.event_id),
                        payment_id=str(event.payment_id),
                    )

                except Exception as e:
                    logger.error(
                        "Failed to publish event",
                        message_id=str(message.id),
                        error=str(e),
                        exc_info=True,
                    )
                    raise

            message_ids = [msg.id for msg in messages]
            await outbox_repo.mark_as_processed(message_ids)

            logger.info("Marked messages as processed", count=len(message_ids))

            return len(messages)


async def outbox_worker_loop() -> None:
    """Основной цикл Outbox Worker."""
    logger.info(
        "Outbox worker started",
        poll_interval=settings.outbox_poll_interval_seconds,
        batch_size=settings.outbox_batch_size,
    )

    while not shutdown_event.is_set():
        try:
            processed_count = await process_outbox_batch(settings.outbox_batch_size)

            if processed_count == 0:
                try:
                    await asyncio.wait_for(
                        shutdown_event.wait(),
                        timeout=settings.outbox_poll_interval_seconds,
                    )
                except asyncio.TimeoutError:
                    pass

        except Exception as e:
            logger.error("Outbox worker error", error=str(e), exc_info=True)
            try:
                await asyncio.wait_for(
                    shutdown_event.wait(), timeout=settings.outbox_poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass


def handle_shutdown(signum: int, frame: Any) -> None:
    """Обработчик сигналов для graceful shutdown."""
    logger.info("Received shutdown signal", signal=signum)
    shutdown_event.set()


async def main() -> None:
    """Главная функция Outbox Worker."""
    signal.signal(signal.SIGINT, handle_shutdown)
    signal.signal(signal.SIGTERM, handle_shutdown)

    logger.info("Setting up RabbitMQ topology...")
    await setup_rabbitmq_topology()
    logger.info("RabbitMQ topology created successfully")

    logger.info("Connecting to RabbitMQ broker...")
    await broker.connect()
    logger.info("Connected to RabbitMQ successfully")

    try:
        await outbox_worker_loop()
    finally:
        await broker.close()
        logger.info("Outbox worker stopped")


if __name__ == "__main__":
    setup_logging()
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"CRITICAL WORKER ERROR: {type(e).__name__}: {e}", flush=True)
        import traceback

        traceback.print_exc()
        sys.exit(1)
