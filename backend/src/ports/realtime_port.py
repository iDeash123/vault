import uuid
from collections.abc import AsyncGenerator
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class RealtimeBrokerPort(Protocol):
    async def publish(self, channel: str, message: dict[str, Any]) -> None: ...

    def subscribe(self, channel: str) -> AsyncGenerator[dict[str, Any], None]: ...

    async def broadcast_lot_event(
        self,
        lot_id: uuid.UUID,
        event: dict[str, Any],
    ) -> None: ...

    async def send_user_notification(
        self,
        user_id: uuid.UUID,
        event: dict[str, Any],
    ) -> None: ...
