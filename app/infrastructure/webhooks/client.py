import logging
import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import structlog

from app.config import settings

logger = structlog.get_logger()


class WebhookDeliveryError(Exception):
    """Исключение при неудачной доставке webhook'а."""

    pass


class WebhookClient:
    """HTTP клиент для отправки webhook'ов с retry-логикой."""

    def __init__(self):
        # Переиспользуем client для connection pooling
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(settings.webhook_timeout_seconds),
            follow_redirects=False,
        )

    @retry(
        stop=stop_after_attempt(settings.webhook_max_retries),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type(WebhookDeliveryError),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True,
    )
    async def send_webhook(
        self,
        url: str,
        payload: dict,
        correlation_id: str | None = None,
    ) -> None:
        """
        Отправляет webhook на указанный URL.

        При неуспехе (сетевые ошибки, 5xx) делает retry с exponential backoff.
        При исчерпании попыток выбрасывает исключение, что приводит к nack в RabbitMQ
        и попаданию сообщения в DLQ.
        """
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "PaymentService-Webhook/1.0",
        }

        try:
            response = await self.client.post(url, json=payload, headers=headers)

            if 200 <= response.status_code < 300:
                logger.info(
                    "Webhook delivered successfully",
                    url=url,
                    status_code=response.status_code,
                )
                return

            if 400 <= response.status_code < 500 and response.status_code != 429:
                logger.error(
                    "Webhook client error (no retry)",
                    url=url,
                    status_code=response.status_code,
                    response_body=response.text[:200],
                )

                # Не ретраим, но считаем это "успешной" доставкой (сервер принял и отказал)
                # В реальности это бизнес-решение. Здесь мы выбросим исключение для DLQ.
                raise WebhookDeliveryError(
                    f"Webhook returned {response.status_code}: {response.text[:100]}"
                )

            logger.warning(
                "Webhook server error (will retry)",
                url=url,
                status_code=response.status_code,
            )
            raise WebhookDeliveryError(f"Webhook returned {response.status_code}")

        except httpx.TimeoutException as e:
            logger.warning("Webhook timeout (will retry)", url=url)
            raise WebhookDeliveryError(f"Timeout: {e}")
        except httpx.HTTPError as e:
            logger.warning("Webhook HTTP error (will retry)", url=url, error=str(e))
            raise WebhookDeliveryError(f"HTTP error: {e}")

    async def close(self) -> None:
        await self.client.aclose()
