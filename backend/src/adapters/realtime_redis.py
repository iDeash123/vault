import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import redis.asyncio as aioredis

from core.config import get_settings
from ports.realtime_port import RealtimeBrokerPort


class RedisRealtimeBrokerAdapter(RealtimeBrokerPort):
    def __init__(self, redis_url: str | None = None) -> None:
        settings = get_settings()
        self.redis_url = redis_url or settings.redis_url_str
        self._client: aioredis.Redis = aioredis.from_url(
            self.redis_url,
            decode_responses=False,
        )

    async def publish(self, channel: str, message: dict[str, Any]) -> None:
        serialized = json.dumps(message).encode("utf-8")
        await self._client.publish(channel, serialized)

    async def subscribe(self, channel: str) -> AsyncGenerator[dict[str, Any], None]:
        pubsub = self._client.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for raw_message in pubsub.listen():
                if raw_message["type"] == "message":
                    payload = raw_message["data"]
                    if isinstance(payload, bytes):
                        decoded: dict[str, Any] = json.loads(payload.decode("utf-8"))
                        yield decoded
                    elif isinstance(payload, str):
                        decoded_str: dict[str, Any] = json.loads(payload)
                        yield decoded_str
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

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

    async def close(self) -> None:
        await self._client.aclose()
