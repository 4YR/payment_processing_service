import uuid
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Middleware для добавления correlation ID к запросам."""

    async def dispatch(self, request: Request, call_next):
        # Получаем correlation ID из заголовка или генерируем новый
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())

        # Добавляем в state для использования в логах
        request.state.correlation_id = correlation_id

        # Выполняем запрос
        response = await call_next(request)

        # Добавляем correlation ID в ответ
        response.headers["X-Correlation-ID"] = correlation_id

        return response
