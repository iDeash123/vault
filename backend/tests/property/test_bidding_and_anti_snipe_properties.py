from datetime import UTC, datetime, timedelta
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from domains.bidding.service import (
    calculate_min_valid_bid,
    compute_is_buy_now_available,
    compute_is_reserve_met,
    evaluate_anti_snipe,
    quantize_usd,
)
from shared.db.models.enums import LotStatus

decimal_price_strategy = st.decimals(
    min_value=Decimal("1.00"),
    max_value=Decimal("500000.00"),
    places=2,
)

decimal_increment_strategy = st.decimals(
    min_value=Decimal("1.00"),
    max_value=Decimal("1000.00"),
    places=2,
)


@given(
    start_price=decimal_price_strategy,
    current_price=decimal_price_strategy,
    min_bid_increment=decimal_increment_strategy,
    bid_count=st.integers(min_value=0, max_value=5000),
)
@settings(max_examples=100)
def test_property_min_valid_bid_calculation(
    start_price: Decimal,
    current_price: Decimal,
    min_bid_increment: Decimal,
    bid_count: int,
) -> None:
    min_bid = calculate_min_valid_bid(
        start_price=start_price,
        current_price=current_price,
        min_bid_increment=min_bid_increment,
        bid_count=bid_count,
    )
    if bid_count == 0:
        assert min_bid == quantize_usd(start_price)
    else:
        assert min_bid == quantize_usd(current_price + min_bid_increment)
        assert min_bid > current_price


@given(
    status=st.sampled_from(list(LotStatus)),
    has_buy_now=st.booleans(),
    has_reserve=st.booleans(),
    bid_count=st.integers(min_value=0, max_value=100),
    base_price=decimal_price_strategy,
    increment=decimal_increment_strategy,
)
@settings(max_examples=150)
def test_property_buy_now_availability_invariants(
    status: LotStatus,
    has_buy_now: bool,
    has_reserve: bool,
    bid_count: int,
    base_price: Decimal,
    increment: Decimal,
) -> None:
    current_price = quantize_usd(base_price)
    min_bid_increment = quantize_usd(increment)
    buy_now_price = (
        quantize_usd(current_price + min_bid_increment + Decimal("50.00")) if has_buy_now else None
    )
    reserve_price = quantize_usd(current_price + Decimal("20.00")) if has_reserve else None

    is_available = compute_is_buy_now_available(
        status=status,
        buy_now_price=buy_now_price,
        reserve_price=reserve_price,
        current_price=current_price,
        min_bid_increment=min_bid_increment,
        bid_count=bid_count,
    )

    if status != LotStatus.LIVE or buy_now_price is None:
        assert is_available is False
        return

    if (current_price + min_bid_increment) >= buy_now_price:
        assert is_available is False
        return

    if bid_count == 0:
        assert is_available is True
        return

    if reserve_price is None:
        assert is_available is False
        return

    if current_price < reserve_price:
        assert is_available is True
    else:
        assert is_available is False


@given(
    base_price=decimal_price_strategy,
    increment=decimal_increment_strategy,
    delta=st.decimals(min_value=Decimal("0.00"), max_value=Decimal("50.00"), places=2),
)
@settings(max_examples=100)
def test_property_buy_now_disappears_when_bid_reaches_or_exceeds_threshold(
    base_price: Decimal,
    increment: Decimal,
    delta: Decimal,
) -> None:
    current_price = quantize_usd(base_price)
    min_increment = quantize_usd(increment)
    buy_now_price = quantize_usd(current_price + min_increment - delta)

    is_available = compute_is_buy_now_available(
        status=LotStatus.LIVE,
        buy_now_price=buy_now_price,
        reserve_price=None,
        current_price=current_price,
        min_bid_increment=min_increment,
        bid_count=0,
    )
    assert is_available is False


@given(
    seconds_remaining=st.integers(min_value=-300, max_value=600),
    initial_extensions=st.integers(min_value=0, max_value=50),
)
@settings(max_examples=150)
def test_property_anti_snipe_trigger_window(
    seconds_remaining: int,
    initial_extensions: int,
) -> None:
    now = datetime(2026, 10, 26, 12, 0, 0, tzinfo=UTC)
    ends_at = now + timedelta(seconds=seconds_remaining)

    new_ends_at, extensions_count, triggered = evaluate_anti_snipe(
        ends_at=ends_at,
        now=now,
        extensions_count=initial_extensions,
        window_seconds=120,
        extension_seconds=120,
    )

    if 0 < seconds_remaining < 120:
        assert triggered is True
        assert extensions_count == initial_extensions + 1
        assert new_ends_at == now + timedelta(seconds=120)
    else:
        assert triggered is False
        assert extensions_count == initial_extensions
        assert new_ends_at == ends_at


@given(
    has_reserve=st.booleans(),
    reserve_offset=st.decimals(min_value=Decimal("-100.00"), max_value=Decimal("100.00"), places=2),
    bid_count=st.integers(min_value=0, max_value=10),
    base_price=decimal_price_strategy,
)
@settings(max_examples=100)
def test_property_reserve_met_logic(
    has_reserve: bool,
    reserve_offset: Decimal,
    bid_count: int,
    base_price: Decimal,
) -> None:
    current_price = quantize_usd(base_price)
    reserve_price = (
        quantize_usd(max(Decimal("1.00"), current_price + reserve_offset)) if has_reserve else None
    )

    is_met = compute_is_reserve_met(
        reserve_price=reserve_price,
        current_price=current_price,
        bid_count=bid_count,
    )

    if reserve_price is None:
        assert is_met is True
    elif bid_count == 0:
        assert is_met is False
    else:
        assert is_met == (current_price >= reserve_price)
