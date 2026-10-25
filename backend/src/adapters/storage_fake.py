from core.exceptions import NotFoundError
from ports.storage_port import StoragePort, validate_image_bytes


class InMemoryStorageAdapter(StoragePort):
    def __init__(self, base_url: str = "http://localhost:9000/obsolete-media") -> None:
        self.base_url = base_url.rstrip("/")
        self._storage: dict[str, bytes] = {}
        self._content_types: dict[str, str] = {}

    async def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        detected_mime = validate_image_bytes(data)
        self._storage[key] = data
        self._content_types[key] = content_type or detected_mime
        return self.get_public_url(key)

    async def download(self, key: str) -> bytes:
        if key not in self._storage:
            raise NotFoundError(
                message=f"Storage object '{key}' not found",
                error_code="STORAGE_OBJECT_NOT_FOUND",
            )
        return self._storage[key]

    async def delete(self, key: str) -> None:
        self._storage.pop(key, None)
        self._content_types.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._storage

    def get_public_url(self, key: str) -> str:
        return f"{self.base_url}/{key.lstrip('/')}"
