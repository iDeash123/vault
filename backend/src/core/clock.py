from datetime import UTC, datetime
from typing import Protocol


class ClockPort(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)


class FrozenClock:
    def __init__(self, current_time: datetime) -> None:
        self._current_time = current_time

    def set_time(self, new_time: datetime) -> None:
        self._current_time = new_time

    def now(self) -> datetime:
        return self._current_time
