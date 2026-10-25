import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from shared.db.models import (
    EscrowOrder,
    EscrowOrderStatus,
    Lot,
    LotCategory,
    LotMedia,
    LotStatus,
    MediaSlotType,
    User,
    UserRole,
    Wallet,
    WalletHold,
    WalletHoldStatus,
)


async def create_test_user(
    session: AsyncSession,
    email: str = "collector@obsolete.io",
    username: str = "collector",
) -> User:
    user = User(
        email=email,
        username=username,
        password_hash="argon2id$mockhash",
        role=UserRole.MEMBER,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def create_test_wallet(
    session: AsyncSession,
    user: User,
    available: Decimal = Decimal("1000.00"),
) -> Wallet:
    wallet = Wallet(
        user_id=user.id,
        currency="USD",
        available_balance=available,
        held_balance=Decimal("0.00"),
        claimable_balance=Decimal("0.00"),
    )
    session.add(wallet)
    await session.commit()
    await session.refresh(wallet)
    return wallet


async def create_test_lot(
    session: AsyncSession,
    seller: User,
    start_price: Decimal = Decimal("500.00"),
    reserve_price: Decimal | None = Decimal("700.00"),
    buy_now_price: Decimal | None = Decimal("1200.00"),
    min_bid_increment: Decimal = Decimal("25.00"),
) -> Lot:
    now = datetime.now(UTC)
    lot = Lot(
        seller_id=seller.id,
        category=LotCategory.APPAREL,
        status=LotStatus.LIVE,
        title="Raf Simons AW01 Riot Riot Riot Bomber",
        subtitle="Iconic archival camouflage bomber jacket",
        description="Museum grade condition collector artifact.",
        specs={
            "brand": "Raf Simons",
            "season_era": "AW01 Riot! Riot! Riot!",
            "tagged_size": "48",
            "condition_grade": "ARCHIVAL_MINT",
            "measurements_cm": {
                "chest": 62.0,
                "shoulders": 54.0,
                "length": 71.0,
                "sleeve": 66.0,
            },
            "materials": ["Cotton", "Polyester"],
        },
        start_price=start_price,
        reserve_price=reserve_price,
        buy_now_price=buy_now_price,
        min_bid_increment=min_bid_increment,
        current_price=start_price,
        bid_count=0,
        anti_snipe_extensions_count=0,
        starts_at=now,
        ends_at=now + timedelta(days=3),
    )
    session.add(lot)
    await session.commit()
    await session.refresh(lot)
    return lot


@pytest.mark.asyncio
async def test_uq_active_hold_per_lot_prevents_duplicate_active_holds(
    db_session: AsyncSession,
) -> None:
    seller = await create_test_user(db_session, "seller1@obsolete.io", "seller1")
    bidder_a = await create_test_user(db_session, "bidder_a@obsolete.io", "bidder_a")
    bidder_b = await create_test_user(db_session, "bidder_b@obsolete.io", "bidder_b")

    wallet_a = await create_test_wallet(db_session, bidder_a)
    wallet_b = await create_test_wallet(db_session, bidder_b)
    lot = await create_test_lot(db_session, seller)

    hold_a = WalletHold(
        wallet_id=wallet_a.id,
        user_id=bidder_a.id,
        lot_id=lot.id,
        amount=Decimal("500.00"),
        status=WalletHoldStatus.ACTIVE_HOLD,
    )
    db_session.add(hold_a)
    await db_session.commit()

    hold_b = WalletHold(
        wallet_id=wallet_b.id,
        user_id=bidder_b.id,
        lot_id=lot.id,
        amount=Decimal("525.00"),
        status=WalletHoldStatus.ACTIVE_HOLD,
    )
    db_session.add(hold_b)

    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()

    await db_session.rollback()
    assert "uq_active_hold_per_lot" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_multiple_claimable_holds_allowed_for_same_user_and_lot(
    db_session: AsyncSession,
) -> None:
    seller = await create_test_user(db_session, "seller2@obsolete.io", "seller2")
    bidder = await create_test_user(db_session, "bidder2@obsolete.io", "bidder2")
    wallet = await create_test_wallet(db_session, bidder)
    lot = await create_test_lot(db_session, seller)

    hold_1 = WalletHold(
        wallet_id=wallet.id,
        user_id=bidder.id,
        lot_id=lot.id,
        amount=Decimal("500.00"),
        status=WalletHoldStatus.CLAIMABLE,
    )
    hold_2 = WalletHold(
        wallet_id=wallet.id,
        user_id=bidder.id,
        lot_id=lot.id,
        amount=Decimal("550.00"),
        status=WalletHoldStatus.CLAIMABLE,
    )
    hold_3 = WalletHold(
        wallet_id=wallet.id,
        user_id=bidder.id,
        lot_id=lot.id,
        amount=Decimal("600.00"),
        status=WalletHoldStatus.CLAIMABLE,
    )

    db_session.add_all([hold_1, hold_2, hold_3])
    await db_session.commit()

    stmt = select(WalletHold).where(
        WalletHold.user_id == bidder.id,
        WalletHold.lot_id == lot.id,
        WalletHold.status == WalletHoldStatus.CLAIMABLE,
    )
    result = await db_session.execute(stmt)
    persisted_holds = result.scalars().all()
    assert len(persisted_holds) == 3


@pytest.mark.asyncio
async def test_wallet_non_negative_balance_check_constraints(
    db_session: AsyncSession,
) -> None:
    user_a = await create_test_user(db_session, "wallet_user_a@obsolete.io", "wallet_user_a")
    wallet_a = await create_test_wallet(db_session, user_a, available=Decimal("100.00"))
    wallet_a.available_balance = Decimal("-0.01")
    with pytest.raises(IntegrityError) as exc_info_available:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_wallets_available_non_negative" in str(exc_info_available.value).lower()

    user_b = await create_test_user(db_session, "wallet_user_b@obsolete.io", "wallet_user_b")
    wallet_b = await create_test_wallet(db_session, user_b, available=Decimal("100.00"))
    wallet_b.held_balance = Decimal("-1.00")
    with pytest.raises(IntegrityError) as exc_info_held:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_wallets_held_non_negative" in str(exc_info_held.value).lower()

    user_c = await create_test_user(db_session, "wallet_user_c@obsolete.io", "wallet_user_c")
    wallet_c = await create_test_wallet(db_session, user_c, available=Decimal("100.00"))
    wallet_c.claimable_balance = Decimal("-0.01")
    with pytest.raises(IntegrityError) as exc_info_claimable:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_wallets_claimable_non_negative" in str(exc_info_claimable.value).lower()


@pytest.mark.asyncio
async def test_lot_price_and_dates_check_constraints(
    db_session: AsyncSession,
) -> None:
    seller = await create_test_user(db_session, "seller3@obsolete.io", "seller3")
    seller_id = seller.id
    now = datetime.now(UTC)

    lot_invalid_start = Lot(
        seller_id=seller_id,
        category=LotCategory.ARTIFACT,
        status=LotStatus.DRAFT,
        title="Dieter Rams ET66",
        subtitle="Design calculator",
        description="Rare black edition calculator.",
        specs={"designer": "Dieter Rams", "era": "1987"},
        start_price=Decimal("0.00"),
        min_bid_increment=Decimal("10.00"),
        current_price=Decimal("0.00"),
        starts_at=now,
        ends_at=now + timedelta(days=1),
    )
    db_session.add(lot_invalid_start)
    with pytest.raises(IntegrityError) as exc_info_start:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_lots_start_price_positive" in str(exc_info_start.value).lower()

    lot_invalid_increment = Lot(
        seller_id=seller_id,
        category=LotCategory.ARTIFACT,
        status=LotStatus.DRAFT,
        title="Dieter Rams ET66",
        subtitle="Design calculator",
        description="Rare black edition calculator.",
        specs={"designer": "Dieter Rams", "era": "1987"},
        start_price=Decimal("100.00"),
        min_bid_increment=Decimal("0.50"),
        current_price=Decimal("100.00"),
        starts_at=now,
        ends_at=now + timedelta(days=1),
    )
    db_session.add(lot_invalid_increment)
    with pytest.raises(IntegrityError) as exc_info_increment:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_lots_increment_positive" in str(exc_info_increment.value).lower()

    lot_invalid_reserve = Lot(
        seller_id=seller_id,
        category=LotCategory.ARTIFACT,
        status=LotStatus.DRAFT,
        title="Dieter Rams ET66",
        subtitle="Design calculator",
        description="Rare black edition calculator.",
        specs={"designer": "Dieter Rams", "era": "1987"},
        start_price=Decimal("200.00"),
        reserve_price=Decimal("150.00"),
        min_bid_increment=Decimal("10.00"),
        current_price=Decimal("200.00"),
        starts_at=now,
        ends_at=now + timedelta(days=1),
    )
    db_session.add(lot_invalid_reserve)
    with pytest.raises(IntegrityError) as exc_info_reserve:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_lots_reserve_gte_start" in str(exc_info_reserve.value).lower()

    lot_invalid_dates = Lot(
        seller_id=seller_id,
        category=LotCategory.ARTIFACT,
        status=LotStatus.DRAFT,
        title="Dieter Rams ET66",
        subtitle="Design calculator",
        description="Rare black edition calculator.",
        specs={"designer": "Dieter Rams", "era": "1987"},
        start_price=Decimal("200.00"),
        min_bid_increment=Decimal("10.00"),
        current_price=Decimal("200.00"),
        starts_at=now,
        ends_at=now - timedelta(hours=1),
    )
    db_session.add(lot_invalid_dates)
    with pytest.raises(IntegrityError) as exc_info_dates:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_lots_ends_after_starts" in str(exc_info_dates.value).lower()


@pytest.mark.asyncio
async def test_wallet_hold_positive_amount_check(
    db_session: AsyncSession,
) -> None:
    seller = await create_test_user(db_session, "seller4@obsolete.io", "seller4")
    bidder = await create_test_user(db_session, "bidder4@obsolete.io", "bidder4")
    wallet = await create_test_wallet(db_session, bidder)
    lot = await create_test_lot(db_session, seller)

    invalid_hold = WalletHold(
        wallet_id=wallet.id,
        user_id=bidder.id,
        lot_id=lot.id,
        amount=Decimal("0.00"),
        status=WalletHoldStatus.ACTIVE_HOLD,
    )
    db_session.add(invalid_hold)
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_wallet_holds_amount_positive" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_lot_media_size_limit_check(
    db_session: AsyncSession,
) -> None:
    seller = await create_test_user(db_session, "seller5@obsolete.io", "seller5")
    lot = await create_test_lot(db_session, seller)

    invalid_media = LotMedia(
        lot_id=lot.id,
        slot_type=MediaSlotType.PRIMARY,
        storage_key=str(uuid.uuid4()),
        public_url="http://localhost:9000/obsolete-media/oversized.jpg",
        mime_type="image/jpeg",
        size_bytes=10_485_761,
        sort_order=0,
    )
    db_session.add(invalid_media)
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_lot_media_size_limit" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_escrow_order_fee_math_check(
    db_session: AsyncSession,
) -> None:
    seller = await create_test_user(db_session, "seller6@obsolete.io", "seller6")
    buyer = await create_test_user(db_session, "buyer6@obsolete.io", "buyer6")
    wallet = await create_test_wallet(db_session, buyer)
    lot = await create_test_lot(db_session, seller)

    hold = WalletHold(
        wallet_id=wallet.id,
        user_id=buyer.id,
        lot_id=lot.id,
        amount=Decimal("1000.00"),
        status=WalletHoldStatus.CAPTURED_TO_ESCROW,
    )
    db_session.add(hold)
    await db_session.commit()
    await db_session.refresh(hold)

    invalid_order = EscrowOrder(
        lot_id=lot.id,
        buyer_id=buyer.id,
        seller_id=seller.id,
        wallet_hold_id=hold.id,
        final_amount=Decimal("1000.00"),
        platform_fee_amount=Decimal("80.00"),
        seller_payout_amount=Decimal("919.00"),
        status=EscrowOrderStatus.FUNDS_HELD,
    )
    db_session.add(invalid_order)
    with pytest.raises(IntegrityError) as exc_info:
        await db_session.commit()
    await db_session.rollback()
    assert "ck_escrow_fee_math" in str(exc_info.value).lower()
