import asyncio
from typing import Any

import boto3
from botocore.exceptions import ClientError

from core.config import get_settings
from core.exceptions import NotFoundError
from ports.storage_port import StoragePort, validate_image_bytes


class S3StorageAdapter(StoragePort):
    def __init__(
        self,
        endpoint_url: str | None = None,
        public_base_url: str | None = None,
        access_key_id: str | None = None,
        secret_access_key: str | None = None,
        bucket_name: str | None = None,
        region_name: str | None = None,
    ) -> None:
        settings = get_settings()
        self.endpoint_url = endpoint_url or settings.S3_ENDPOINT_URL
        self.public_base_url = (public_base_url or settings.S3_PUBLIC_BASE_URL).rstrip("/")
        self.bucket_name = bucket_name or settings.S3_BUCKET_NAME
        self.region_name = region_name or settings.S3_REGION

        raw_access_key = access_key_id or settings.S3_ACCESS_KEY_ID.get_secret_value()
        raw_secret_key = secret_access_key or settings.S3_SECRET_ACCESS_KEY.get_secret_value()

        self._s3_client: Any = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=raw_access_key,
            aws_secret_access_key=raw_secret_key,
            region_name=self.region_name,
        )

    def _put_object_sync(self, key: str, data: bytes, content_type: str) -> None:
        self._s3_client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
        )

    def _get_object_sync(self, key: str) -> bytes:
        try:
            response = self._s3_client.get_object(Bucket=self.bucket_name, Key=key)
            body = response["Body"].read()
            return bytes(body)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404"}:
                raise NotFoundError(
                    message=f"Storage object '{key}' not found",
                    error_code="STORAGE_OBJECT_NOT_FOUND",
                ) from exc
            raise

    def _delete_object_sync(self, key: str) -> None:
        self._s3_client.delete_object(Bucket=self.bucket_name, Key=key)

    def _head_object_sync(self, key: str) -> bool:
        try:
            self._s3_client.head_object(Bucket=self.bucket_name, Key=key)
            return True
        except ClientError as exc:
            code = str(exc.response.get("Error", {}).get("Code", ""))
            if code in {"404", "NoSuchKey"}:
                return False
            raise

    async def upload(self, key: str, data: bytes, content_type: str | None = None) -> str:
        detected_mime = validate_image_bytes(data)
        final_content_type = content_type or detected_mime
        await asyncio.to_thread(self._put_object_sync, key, data, final_content_type)
        return self.get_public_url(key)

    async def download(self, key: str) -> bytes:
        return await asyncio.to_thread(self._get_object_sync, key)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete_object_sync, key)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(self._head_object_sync, key)

    def get_public_url(self, key: str) -> str:
        return f"{self.public_base_url}/{key.lstrip('/')}"
