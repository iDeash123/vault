from decimal import Decimal
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            Path.cwd() / ".env",
            Path(__file__).resolve().parents[3] / ".env",
        ),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    APP_ENV: str = "development"
    APP_HOST: str = "127.0.0.1"
    APP_PORT: int = 8000
    CORS_ALLOWED_ORIGINS: str = "http://localhost:5173"

    POSTGRES_HOST: str
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str
    POSTGRES_PASSWORD: SecretStr
    POSTGRES_DB: str
    DATABASE_URL: SecretStr
    TEST_DATABASE_URL: SecretStr

    REDIS_URL: SecretStr
    TEST_REDIS_URL: SecretStr

    JWT_SECRET_KEY: SecretStr
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 30
    COOKIE_SECURE: bool = False
    COOKIE_DOMAIN: str = "localhost"

    S3_ENDPOINT_URL: str
    S3_PUBLIC_BASE_URL: str
    S3_ACCESS_KEY_ID: SecretStr
    S3_SECRET_ACCESS_KEY: SecretStr
    S3_BUCKET_NAME: str = "obsolete-media"
    S3_REGION: str = "us-east-1"

    STRIPE_SECRET_KEY: SecretStr
    STRIPE_WEBHOOK_SECRET: SecretStr
    STRIPE_SUCCESS_URL: str
    STRIPE_CANCEL_URL: str

    PLATFORM_FEE_PERCENT: Decimal = Decimal("8.00")
    ANTI_SNIPE_WINDOW_SECONDS: int = 120
    ANTI_SNIPE_EXTENSION_SECONDS: int = 120

    VITE_API_BASE_URL: str = "http://localhost:8000/api/v1"
    VITE_WS_BASE_URL: str = "ws://localhost:8000/ws"
    VITE_STRIPE_PUBLISHABLE_KEY: str = "pk_test_placeholder"

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

    @property
    def database_url_str(self) -> str:
        return self.DATABASE_URL.get_secret_value()

    @property
    def test_database_url_str(self) -> str:
        return self.TEST_DATABASE_URL.get_secret_value()

    @property
    def redis_url_str(self) -> str:
        return self.REDIS_URL.get_secret_value()

    @property
    def test_redis_url_str(self) -> str:
        return self.TEST_REDIS_URL.get_secret_value()


@lru_cache
def get_settings() -> Settings:
    return Settings()
