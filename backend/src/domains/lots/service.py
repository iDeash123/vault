import uuid
from datetime import UTC
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from core.clock import ClockPort
from core.exceptions import ConflictError, DomainError, ForbiddenError, NotFoundError
from domains.lots.repository import LotRepository
from domains.lots.schemas import (
    CreateLotRequest,
    LotMediaItemResponse,
    LotMediaUploadResponse,
    LotResponse,
)
from ports.storage_port import StoragePort, validate_image_bytes
from shared.db.models.enums import LotStatus, MediaSlotType
from shared.db.models.lot import Lot, LotMedia
from shared.schemas.specs import LotSpecs, lot_specs_adapter

MANDATORY_MEDIA_SLOTS = {
    MediaSlotType.PRIMARY,
    MediaSlotType.TAG_STAMP,
    MediaSlotType.DEFECT,
    MediaSlotType.DETAIL,
}


class LotService:
    def __init__(
        self,
        session: AsyncSession,
        clock: ClockPort,
        storage: StoragePort,
    ) -> None:
        self.session = session
        self.clock = clock
        self.storage = storage
        self.repository = LotRepository(session)

    def build_lot_response(self, lot: Lot) -> LotResponse:
        if lot.bid_count == 0:
            min_valid_bid = lot.start_price
        else:
            min_valid_bid = lot.current_price + lot.min_bid_increment

        is_buy_now_available = (
            lot.status == LotStatus.LIVE
            and lot.buy_now_price is not None
            and (
                lot.bid_count == 0
                or (lot.reserve_price is not None and lot.current_price < lot.reserve_price)
            )
            and (lot.current_price + lot.min_bid_increment < lot.buy_now_price)
        )

        is_reserve_met = lot.reserve_price is None or (
            lot.bid_count > 0 and lot.current_price >= lot.reserve_price
        )

        media_items = [
            LotMediaItemResponse(
                id=m.id,
                slot_type=m.slot_type,
                public_url=m.public_url,
                mime_type=m.mime_type,
                sort_order=m.sort_order,
            )
            for m in sorted(lot.media, key=lambda x: x.sort_order)
        ]

        validated_specs: LotSpecs = lot_specs_adapter.validate_python(lot.specs)

        return LotResponse(
            id=lot.id,
            seller_id=lot.seller_id,
            leader_user_id=lot.leader_user_id,
            category=lot.category,
            status=lot.status,
            title=lot.title,
            subtitle=lot.subtitle,
            description=lot.description,
            specs=validated_specs,
            start_price=lot.start_price,
            reserve_price=lot.reserve_price,
            buy_now_price=lot.buy_now_price,
            min_bid_increment=lot.min_bid_increment,
            current_price=lot.current_price,
            min_valid_bid=min_valid_bid,
            bid_count=lot.bid_count,
            is_buy_now_available=is_buy_now_available,
            is_reserve_met=is_reserve_met,
            anti_snipe_extensions_count=lot.anti_snipe_extensions_count,
            starts_at=lot.starts_at,
            ends_at=lot.ends_at,
            media=media_items,
            server_time=self.clock.now(),
        )

    async def create_lot_draft(
        self,
        user_id: uuid.UUID,
        payload: CreateLotRequest,
    ) -> LotResponse:
        if payload.specs.category != payload.category:
            raise DomainError(
                message=(
                    f"Specs category '{payload.specs.category.value}' "
                    f"does not match lot category '{payload.category.value}'"
                ),
                error_code="SPECS_CATEGORY_MISMATCH",
                status_code=400,
            )

        if payload.reserve_price is not None and payload.reserve_price < payload.start_price:
            raise DomainError(
                message="reserve_price must be greater than or equal to start_price",
                error_code="INVALID_RESERVE_PRICE",
                status_code=400,
            )

        effective_reserve = (
            payload.reserve_price if payload.reserve_price is not None else payload.start_price
        )
        if (
            payload.buy_now_price is not None
            and payload.buy_now_price <= effective_reserve + payload.min_bid_increment
        ):
            raise DomainError(
                message=(
                    "buy_now_price must be strictly greater than "
                    "reserve_price (or start_price) + min_bid_increment"
                ),
                error_code="INVALID_BUY_NOW_PRICE",
                status_code=400,
            )

        starts_at = (
            payload.starts_at
            if payload.starts_at.tzinfo is not None
            else payload.starts_at.replace(tzinfo=UTC)
        )
        ends_at = (
            payload.ends_at
            if payload.ends_at.tzinfo is not None
            else payload.ends_at.replace(tzinfo=UTC)
        )

        if ends_at <= starts_at:
            raise DomainError(
                message="ends_at must be strictly after starts_at",
                error_code="INVALID_LOT_TIMING",
                status_code=400,
            )

        specs_dict = payload.specs.model_dump(mode="json")

        lot = Lot(
            id=uuid.uuid4(),
            seller_id=user_id,
            leader_user_id=None,
            category=payload.category,
            status=LotStatus.DRAFT,
            title=payload.title,
            subtitle=payload.subtitle,
            description=payload.description,
            specs=specs_dict,
            start_price=payload.start_price,
            reserve_price=payload.reserve_price,
            buy_now_price=payload.buy_now_price,
            min_bid_increment=payload.min_bid_increment,
            current_price=Decimal("0.00"),
            bid_count=0,
            anti_snipe_extensions_count=0,
            starts_at=starts_at,
            ends_at=ends_at,
            version=1,
        )

        await self.repository.create_lot(lot)
        await self.session.commit()
        refreshed_lot = await self.repository.get_lot_by_id(lot.id)
        if refreshed_lot is None:
            raise NotFoundError(message="Lot not found", error_code="LOT_NOT_FOUND")
        return self.build_lot_response(refreshed_lot)

    async def upload_media(
        self,
        user_id: uuid.UUID,
        lot_id: uuid.UUID,
        slot_type: MediaSlotType,
        file_bytes: bytes,
    ) -> LotMediaUploadResponse:
        lot = await self.repository.get_lot_by_id_for_update(lot_id)
        if lot is None:
            raise NotFoundError(message="Lot not found", error_code="LOT_NOT_FOUND")

        if lot.seller_id != user_id:
            raise ForbiddenError(
                message="You are not the seller of this lot",
                error_code="LOT_ACCESS_FORBIDDEN",
            )

        if lot.status != LotStatus.DRAFT:
            raise ConflictError(
                message="Only draft lots can accept media uploads",
                error_code="LOT_NOT_IN_DRAFT",
            )

        if len(lot.media) >= 8:
            raise DomainError(
                message="Lot cannot have more than 8 media items",
                error_code="LOT_MEDIA_LIMIT_EXCEEDED",
                status_code=400,
            )

        detected_mime = validate_image_bytes(file_bytes)
        ext = "jpg"
        if detected_mime == "image/png":
            ext = "png"
        elif detected_mime == "image/webp":
            ext = "webp"

        media_id = uuid.uuid4()
        storage_key = f"lots/{lot.id}/{slot_type.value.lower()}_{media_id.hex[:12]}.{ext}"
        public_url = await self.storage.upload(
            key=storage_key,
            data=file_bytes,
            content_type=detected_mime,
        )

        sort_order = len(lot.media)
        media = LotMedia(
            id=media_id,
            lot_id=lot.id,
            slot_type=slot_type,
            storage_key=storage_key,
            public_url=public_url,
            mime_type=detected_mime,
            size_bytes=len(file_bytes),
            sort_order=sort_order,
        )

        saved_media = await self.repository.add_media(media)
        await self.session.commit()

        return LotMediaUploadResponse(
            id=saved_media.id,
            lot_id=saved_media.lot_id,
            slot_type=saved_media.slot_type,
            storage_key=saved_media.storage_key,
            public_url=saved_media.public_url,
            mime_type=saved_media.mime_type,
            size_bytes=saved_media.size_bytes,
            sort_order=saved_media.sort_order,
            server_time=self.clock.now(),
        )

    async def submit_lot(
        self,
        user_id: uuid.UUID,
        lot_id: uuid.UUID,
    ) -> LotResponse:
        lot = await self.repository.get_lot_by_id_for_update(lot_id)
        if lot is None:
            raise NotFoundError(message="Lot not found", error_code="LOT_NOT_FOUND")

        if lot.seller_id != user_id:
            raise ForbiddenError(
                message="You are not the seller of this lot",
                error_code="LOT_ACCESS_FORBIDDEN",
            )

        if lot.status != LotStatus.DRAFT:
            raise ConflictError(
                message="Only draft lots can be submitted for review",
                error_code="LOT_NOT_IN_DRAFT",
            )

        media_list = lot.media
        count = len(media_list)
        if count < 4:
            raise DomainError(
                message=(
                    "Lot must have between 4 and 8 photos before submitting "
                    f"(currently has {count})"
                ),
                error_code="INSUFFICIENT_LOT_MEDIA",
                status_code=400,
                details={"current_count": count, "required_min": 4, "required_max": 8},
            )

        if count > 8:
            raise DomainError(
                message=f"Lot cannot have more than 8 photos (currently has {count})",
                error_code="TOO_MANY_LOT_MEDIA",
                status_code=400,
                details={"current_count": count, "required_min": 4, "required_max": 8},
            )

        present_slots = {m.slot_type for m in media_list}
        missing_slots = MANDATORY_MEDIA_SLOTS - present_slots
        if missing_slots:
            missing_list = [s.value for s in sorted(missing_slots)]
            raise DomainError(
                message=f"Lot is missing mandatory media slots: {', '.join(missing_list)}",
                error_code="MISSING_MANDATORY_MEDIA_SLOTS",
                status_code=400,
                details={"missing_slots": missing_list},
            )

        lot.status = LotStatus.PENDING_REVIEW
        lot.updated_at = self.clock.now()
        await self.session.commit()

        refreshed_lot = await self.repository.get_lot_by_id(lot.id)
        if refreshed_lot is None:
            raise NotFoundError(message="Lot not found", error_code="LOT_NOT_FOUND")

        return self.build_lot_response(refreshed_lot)
