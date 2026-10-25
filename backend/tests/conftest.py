from collections.abc import AsyncGenerator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from core.config import Settings, get_settings


@pytest.fixture(scope="session")
def settings() -> Settings:
    return get_settings()


@pytest.fixture(scope="session")
def migrated_test_db(settings: Settings) -> None:
    backend_dir = Path(__file__).resolve().parent.parent
    ini_path = backend_dir / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(backend_dir / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.test_database_url_str)
    command.upgrade(cfg, "head")


@pytest.fixture
async def db_engine(
    settings: Settings,
    migrated_test_db: None,
) -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(settings.test_database_url_str, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    session_factory = async_sessionmaker(
        bind=db_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture(autouse=True)
async def clean_database_tables(db_engine: AsyncEngine) -> AsyncGenerator[None, None]:
    yield
    async with db_engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE TABLE users, refresh_sessions, wallets, lots, lot_media, "
                "wallet_holds, bids, wallet_ledger_entries, stripe_webhook_events, "
                "escrow_orders, watchlist_items, moderation_logs CASCADE;"
            )
        )
