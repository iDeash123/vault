import asyncio
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator
from typing import Any

from ports.realtime_port import RealtimeBrokerPort


class InMemoryRealtimeBrokerAdapter(RealtimeBrokerPort):
    def __init__(self) -> None:
        self.published_events: list[tuple[str, dict[str, Any]]] = []
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        self.published_events.append((channel, dict(message)))
        queues = self._subscribers.get(channel, [])
        for queue in queues:
            await queue.put(dict(message))

    async def subscribe(self, channel: str) -> AsyncGenerator[dict[str, Any], None]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers[channel].append(queue)
        try:
            while True:
                msg = await queue.get()
                yield msg
        finally:
            if queue in self._subscribers[channel]:
                self._subscribers[channel].remove(queue)

    async def broadcast_lot_event(
        self,
        lot_id: uuid.UUID,
        event: dict[str, Any],
    ) -> None:
        await self.publish(f"lot:{lot_id}", event)

    async def send_user_notification(
        self,
        user_id: uuid.UUID,
        event: dict[str, Any],
    ) -> None:
        await self.publish(f"user:{user_id}", event)

    def get_published_events(self, channel: str | None = None) -> list[dict[str, Any]]:
        if channel is None:
            return [evt for _, evt in self.published_events]
        return [evt for ch, evt in self.published_events if ch == channel]
