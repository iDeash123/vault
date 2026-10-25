from typing import Protocol, runtime_checkable

from core.exceptions import DomainError

MAX_MEDIA_SIZE_BYTES = 10_485_760
JPEG_SIGNATURE = b"\xff\xd8\xff"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WEBP_HEADER = b"RIFF"
WEBP_SIGNATURE = b"WEBP"


def validate_image_bytes(data: bytes) -> str:
    if len(data) > MAX_MEDIA_SIZE_BYTES:
        raise DomainError(
            message=f"Media size {len(data)} exceeds maximum allowed {MAX_MEDIA_SIZE_BYTES} bytes",
            error_code="MEDIA_SIZE_LIMIT_EXCEEDED",
            status_code=400,
            details={"max_bytes": MAX_MEDIA_SIZE_BYTES, "received_bytes": len(data)},
        )
    if len(data) < 12:
        raise DomainError(
            message="Media payload too small to be a valid image",
            error_code="INVALID_MEDIA_BYTES",
            status_code=400,
        )
    if data[:3] == JPEG_SIGNATURE:
        return "image/jpeg"
    if data[:8] == PNG_SIGNATURE:
        return "image/png"
    if data[:4] == WEBP_HEADER and data[8:12] == WEBP_SIGNATURE:
        return "image/webp"
    raise DomainError(
        message="Only JPEG, PNG, and WEBP image files are accepted",
        error_code="INVALID_MEDIA_MAGIC_BYTES",
        status_code=400,
    )


@runtime_checkable
class StoragePort(Protocol):
    async def upload(self, key: str, data: bytes, content_type: str | None = None) -> str: ...

    async def download(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def exists(self, key: str) -> bool: ...

    def get_public_url(self, key: str) -> str: ...
