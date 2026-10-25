from taskiq import AsyncBroker, InMemoryBroker
from taskiq_redis import ListQueueBroker

from core.config import get_settings


def create_broker(redis_url: str | None = None, in_memory: bool = False) -> AsyncBroker:
    settings = get_settings()
    if in_memory or settings.APP_ENV == "test":
        return InMemoryBroker()
    url = redis_url or settings.redis_url_str
    return ListQueueBroker(url)


broker: AsyncBroker = create_broker()
