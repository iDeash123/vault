import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from adapters.storage_s3 import S3StorageAdapter
from core.clock import ClockPort
from domains.auth.dependencies import get_clock, get_current_user
from domains.lots.schemas import (
    CreateLotRequest,
    LotMediaUploadResponse,
    LotResponse,
)
from domains.lots.service import LotService
from ports.storage_port import StoragePort
from shared.db.models.enums import MediaSlotType
from shared.db.models.user import User
from shared.db.session import get_db_session

router = APIRouter(prefix="/api/v1", tags=["lots"])


def get_storage_port() -> StoragePort:
    return S3StorageAdapter()


def get_lot_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    clock: Annotated[ClockPort, Depends(get_clock)],
    storage: Annotated[StoragePort, Depends(get_storage_port)],
) -> LotService:
    return LotService(
        session=session,
        clock=clock,
        storage=storage,
    )


@router.post(
    "/lots",
    response_model=LotResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_lot(
    payload: CreateLotRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LotService, Depends(get_lot_service)],
) -> LotResponse:
    return await service.create_lot_draft(
        user_id=current_user.id,
        payload=payload,
    )


@router.post(
    "/lots/{lot_id}/media",
    response_model=LotMediaUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_lot_media(
    lot_id: uuid.UUID,
    slot_type: Annotated[MediaSlotType, Form()],
    file: Annotated[UploadFile, File()],
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LotService, Depends(get_lot_service)],
) -> LotMediaUploadResponse:
    file_bytes = await file.read()
    return await service.upload_media(
        user_id=current_user.id,
        lot_id=lot_id,
        slot_type=slot_type,
        file_bytes=file_bytes,
    )


@router.post(
    "/lots/{lot_id}/submit",
    response_model=LotResponse,
    status_code=status.HTTP_200_OK,
)
async def submit_lot(
    lot_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    service: Annotated[LotService, Depends(get_lot_service)],
) -> LotResponse:
    return await service.submit_lot(
        user_id=current_user.id,
        lot_id=lot_id,
    )
