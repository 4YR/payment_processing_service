import uuid
from fastapi import APIRouter, Depends, status, Header, HTTPException
import structlog

from app.application.dtos import CreatePaymentRequest, PaymentResponse, ErrorResponse
from app.application.services.payment_service import PaymentService
from app.application.ports.unit_of_work import AbstractUnitOfWork
from app.presentation.api.deps import get_uow, verify_api_key

logger = structlog.get_logger()

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post(
    "",
    response_model=PaymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        200: {"model": PaymentResponse, "description": "Idempotent response"},
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def create_payment(
    request: CreatePaymentRequest,
    uow: AbstractUnitOfWork = Depends(get_uow),
    _: str = Depends(verify_api_key),
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    """
    Создает новый платеж.
    """
    service = PaymentService(uow)

    try:
        payment, is_new = await service.create_payment(request, idempotency_key)

        if not is_new:
            return PaymentResponse.model_validate(payment)

        return PaymentResponse.model_validate(payment)

    except Exception as e:
        logger.error("Failed to create payment", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create payment",
        )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    responses={
        404: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
    },
)
async def get_payment(
    payment_id: uuid.UUID,
    uow: AbstractUnitOfWork = Depends(get_uow),
    _: str = Depends(verify_api_key),
):
    """Получает информацию о платеже по ID."""
    service = PaymentService(uow)
    payment = await service.get_payment(payment_id)

    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Payment with id {payment_id} not found",
        )

    return PaymentResponse.model_validate(payment)
