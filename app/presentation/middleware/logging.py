import time
from fastapi import Request
import structlog
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware для логирования запросов."""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        correlation_id = getattr(request.state, "correlation_id", None)

        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        logger.info("Request started")

        try:
            response = await call_next(request)
            process_time = time.time() - start_time

            logger.info(
                "Request completed",
                status_code=response.status_code,
                process_time=round(process_time, 3),
            )
            return response

        except Exception as e:
            process_time = time.time() - start_time
            logger.error(
                "Request failed",
                error=str(e),
                process_time=round(process_time, 3),
                exc_info=True,
            )
            raise

        finally:
            structlog.contextvars.clear_contextvars()
