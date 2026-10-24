import uuid

from sqlalchemy import Enum, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from shared.db.base import Base, CreatedAtMixin, UUIDpk
from shared.db.models.enums import ModerationDecision


class ModerationLog(Base, CreatedAtMixin):
    __tablename__ = "moderation_logs"

    id: Mapped[UUIDpk]
    lot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lots.id", ondelete="CASCADE"),
        nullable=False,
    )
    curator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[ModerationDecision] = mapped_column(
        Enum(ModerationDecision, native_enum=False, length=32),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
