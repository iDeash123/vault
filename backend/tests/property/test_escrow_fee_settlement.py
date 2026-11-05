from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from domains.escrow.service import calculate_platform_fee_and_payout, quantize_usd

amount_strategy = st.decimals(
    min_value=Decimal("0.01"),
    max_value=Decimal("10000000.00"),
    places=2,
)

fee_percent_strategy = st.decimals(
    min_value=Decimal("0.00"),
    max_value=Decimal("100.00"),
    places=2,
)


@given(final_amount=amount_strategy, fee_percent=fee_percent_strategy)
@settings(max_examples=500)
def test_escrow_fee_settlement_math_exact_conservation(
    final_amount: Decimal,
    fee_percent: Decimal,
) -> None:
    platform_fee, seller_payout = calculate_platform_fee_and_payout(
        final_amount=final_amount,
        fee_percent=fee_percent,
    )

    quantized_final = quantize_usd(final_amount)
    assert platform_fee + seller_payout == quantized_final
    assert platform_fee >= Decimal("0.00")
    assert seller_payout >= Decimal("0.00")
    assert platform_fee == quantize_usd(platform_fee)
    assert seller_payout == quantize_usd(seller_payout)


@given(final_amount=amount_strategy)
@settings(max_examples=300)
def test_escrow_fee_settlement_default_eight_percent(final_amount: Decimal) -> None:
    platform_fee, seller_payout = calculate_platform_fee_and_payout(
        final_amount=final_amount,
        fee_percent=Decimal("8.00"),
    )

    quantized_final = quantize_usd(final_amount)
    assert platform_fee + seller_payout == quantized_final
    assert platform_fee <= quantized_final
    assert seller_payout <= quantized_final


def test_escrow_fee_settlement_edge_cases() -> None:
    cases = [
        (Decimal("0.01"), Decimal("8.00"), Decimal("0.00"), Decimal("0.01")),
        (Decimal("0.06"), Decimal("8.00"), Decimal("0.00"), Decimal("0.06")),
        (Decimal("0.07"), Decimal("8.00"), Decimal("0.01"), Decimal("0.06")),
        (Decimal("1.00"), Decimal("8.00"), Decimal("0.08"), Decimal("0.92")),
        (Decimal("12.50"), Decimal("8.00"), Decimal("1.00"), Decimal("11.50")),
        (Decimal("99.99"), Decimal("8.00"), Decimal("8.00"), Decimal("91.99")),
        (Decimal("100.00"), Decimal("8.00"), Decimal("8.00"), Decimal("92.00")),
        (Decimal("4200.00"), Decimal("8.00"), Decimal("336.00"), Decimal("3864.00")),
        (Decimal("10000.00"), Decimal("0.00"), Decimal("0.00"), Decimal("10000.00")),
        (Decimal("10000.00"), Decimal("100.00"), Decimal("10000.00"), Decimal("0.00")),
    ]

    for final_amt, rate, expected_fee, expected_payout in cases:
        fee, payout = calculate_platform_fee_and_payout(final_amt, rate)
        assert fee == expected_fee
        assert payout == expected_payout
        assert fee + payout == final_amt


@given(
    buyer_held=st.decimals(min_value=Decimal("100.00"), max_value=Decimal("50000.00"), places=2),
    seller_avail=st.decimals(min_value=Decimal("0.00"), max_value=Decimal("50000.00"), places=2),
    order_amount=st.decimals(min_value=Decimal("1.00"), max_value=Decimal("100.00"), places=2),
    fee_percent=fee_percent_strategy,
)
@settings(max_examples=300)
def test_simulated_settlement_total_value_conservation(
    buyer_held: Decimal,
    seller_avail: Decimal,
    order_amount: Decimal,
    fee_percent: Decimal,
) -> None:
    buyer_held_initial = quantize_usd(buyer_held)
    seller_avail_initial = quantize_usd(seller_avail)
    final_amount = quantize_usd(order_amount)

    fee, payout = calculate_platform_fee_and_payout(final_amount, fee_percent)

    buyer_held_after = buyer_held_initial - final_amount
    seller_avail_after = seller_avail_initial + payout

    total_before = buyer_held_initial + seller_avail_initial
    total_after = buyer_held_after + seller_avail_after + fee

    assert total_before == total_after
