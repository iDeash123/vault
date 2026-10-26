import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from core.exceptions import ConflictError, DomainError
from domains.wallet.service import (
    apply_bid_lock,
    apply_hold_to_claimable,
    apply_manual_hold_claim,
    apply_wallet_topup,
    quantize_usd,
)
from shared.db.models.enums import LedgerEntryType, WalletHoldStatus
from shared.db.models.wallet import Wallet, WalletHold, WalletLedgerEntry

OperationKind = Literal[
    "TOPUP",
    "PLACE_BID",
    "OUTBID",
    "SELF_OUTBID",
    "MANUAL_CLAIM",
    "DUPLICATE_CLAIM",
    "CLAIM_ALL",
]


@dataclass(frozen=True)
class LedgerOperationStep:
    kind: OperationKind
    amount_cents: int
    hold_selector: int


operation_step_strategy = st.builds(
    LedgerOperationStep,
    kind=st.sampled_from(
        [
            "TOPUP",
            "PLACE_BID",
            "OUTBID",
            "SELF_OUTBID",
            "MANUAL_CLAIM",
            "DUPLICATE_CLAIM",
            "CLAIM_ALL",
        ]
    ),
    amount_cents=st.integers(min_value=100, max_value=250_000),
    hold_selector=st.integers(min_value=0, max_value=20),
)


class WalletLedgerHarness:
    def __init__(self, user_id: uuid.UUID, lot_id: uuid.UUID, now: datetime) -> None:
        self.user_id = user_id
        self.lot_id = lot_id
        self.now = now
        self.wallet = Wallet(
            id=uuid.uuid4(),
            user_id=user_id,
            currency="USD",
            available_balance=Decimal("0.00"),
            held_balance=Decimal("0.00"),
            claimable_balance=Decimal("0.00"),
            updated_at=now,
        )
        self.holds: list[WalletHold] = []
        self.ledger: list[WalletLedgerEntry] = []
        self._seq = 0

    def _record_entry(
        self,
        entry_type: LedgerEntryType,
        amount: Decimal,
        avail_delta: Decimal,
        held_delta: Decimal,
        claim_delta: Decimal,
        hold_id: uuid.UUID | None = None,
    ) -> None:
        self._seq += 1
        self.ledger.append(
            WalletLedgerEntry(
                id=uuid.uuid4(),
                wallet_id=self.wallet.id,
                user_id=self.user_id,
                entry_type=entry_type,
                amount=amount,
                available_delta=avail_delta,
                held_delta=held_delta,
                claimable_delta=claim_delta,
                balance_available_after=quantize_usd(self.wallet.available_balance),
                balance_held_after=quantize_usd(self.wallet.held_balance),
                balance_claimable_after=quantize_usd(self.wallet.claimable_balance),
                reference_lot_id=self.lot_id if hold_id is not None else None,
                reference_hold_id=hold_id,
                idempotency_key=f"prop_op_{self._seq}",
                created_at=self.now,
            )
        )

    def topup(self, amount: Decimal) -> None:
        avail_d, held_d, claim_d = apply_wallet_topup(
            wallet=self.wallet,
            amount_usd=amount,
            now=self.now,
        )
        self._record_entry(
            entry_type=LedgerEntryType.STRIPE_TOPUP,
            amount=quantize_usd(amount),
            avail_delta=avail_d,
            held_delta=held_d,
            claim_delta=claim_d,
        )

    def lock_bid(self, amount: Decimal) -> WalletHold:
        active_holds = [h for h in self.holds if h.status == WalletHoldStatus.ACTIVE_HOLD]
        for active in active_holds:
            self.outbid_hold(active)

        avail_d, held_d, claim_d = apply_bid_lock(
            wallet=self.wallet,
            amount=amount,
            now=self.now,
        )
        hold = WalletHold(
            id=uuid.uuid4(),
            wallet_id=self.wallet.id,
            user_id=self.user_id,
            lot_id=self.lot_id,
            amount=quantize_usd(amount),
            status=WalletHoldStatus.ACTIVE_HOLD,
            created_at=self.now,
        )
        self.holds.append(hold)
        self._record_entry(
            entry_type=LedgerEntryType.BID_LOCK,
            amount=hold.amount,
            avail_delta=avail_d,
            held_delta=held_d,
            claim_delta=claim_d,
            hold_id=hold.id,
        )
        return hold

    def outbid_hold(self, hold: WalletHold) -> None:
        avail_before = quantize_usd(self.wallet.available_balance)
        avail_d, held_d, claim_d = apply_hold_to_claimable(
            wallet=self.wallet,
            hold=hold,
            now=self.now,
            entry_type=LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
        )
        assert quantize_usd(self.wallet.available_balance) == avail_before
        assert avail_d == Decimal("0.00")
        assert hold.status == WalletHoldStatus.CLAIMABLE
        self._record_entry(
            entry_type=LedgerEntryType.BID_OUTBID_TO_CLAIMABLE,
            amount=quantize_usd(hold.amount),
            avail_delta=avail_d,
            held_delta=held_d,
            claim_delta=claim_d,
            hold_id=hold.id,
        )

    def manual_claim(self, hold: WalletHold) -> None:
        avail_before = quantize_usd(self.wallet.available_balance)
        claimable_before = quantize_usd(self.wallet.claimable_balance)
        amt = quantize_usd(hold.amount)
        avail_d, held_d, claim_d = apply_manual_hold_claim(
            wallet=self.wallet,
            hold=hold,
            requesting_user_id=self.user_id,
            now=self.now,
        )
        assert hold.status == WalletHoldStatus.CLAIMED
        assert hold.claimed_at == self.now
        assert quantize_usd(self.wallet.available_balance) == avail_before + amt
        assert quantize_usd(self.wallet.claimable_balance) == claimable_before - amt
        self._record_entry(
            entry_type=LedgerEntryType.BID_MANUAL_CLAIM,
            amount=amt,
            avail_delta=avail_d,
            held_delta=held_d,
            claim_delta=claim_d,
            hold_id=hold.id,
        )

    def assert_invariants(self) -> None:
        avail = quantize_usd(self.wallet.available_balance)
        held = quantize_usd(self.wallet.held_balance)
        claimable = quantize_usd(self.wallet.claimable_balance)

        assert avail >= Decimal("0.00")
        assert held >= Decimal("0.00")
        assert claimable >= Decimal("0.00")

        sum_avail = sum((quantize_usd(e.available_delta) for e in self.ledger), Decimal("0.00"))
        sum_held = sum((quantize_usd(e.held_delta) for e in self.ledger), Decimal("0.00"))
        sum_claim = sum((quantize_usd(e.claimable_delta) for e in self.ledger), Decimal("0.00"))

        assert avail == sum_avail
        assert held == sum_held
        assert claimable == sum_claim

        active_holds = [h for h in self.holds if h.status == WalletHoldStatus.ACTIVE_HOLD]
        claimable_holds = [h for h in self.holds if h.status == WalletHoldStatus.CLAIMABLE]

        assert len(active_holds) <= 1
        assert held == sum((quantize_usd(h.amount) for h in active_holds), Decimal("0.00"))
        assert claimable == sum((quantize_usd(h.amount) for h in claimable_holds), Decimal("0.00"))

        total_topups = sum(
            (
                quantize_usd(e.amount)
                for e in self.ledger
                if e.entry_type == LedgerEntryType.STRIPE_TOPUP
            ),
            Decimal("0.00"),
        )
        assert avail + held + claimable == total_topups


@settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)
@given(steps=st.lists(operation_step_strategy, min_size=1, max_size=40))
def test_wallet_double_entry_ledger_and_manual_claim_invariants(
    steps: list[LedgerOperationStep],
) -> None:
    now = datetime(2026, 10, 26, 10, 0, 0, tzinfo=UTC)
    harness = WalletLedgerHarness(
        user_id=uuid.uuid4(),
        lot_id=uuid.uuid4(),
        now=now,
    )

    for step in steps:
        amount = quantize_usd(Decimal(step.amount_cents) / Decimal("100"))

        if step.kind == "TOPUP":
            harness.topup(amount)

        elif step.kind == "PLACE_BID":
            active = [h for h in harness.holds if h.status == WalletHoldStatus.ACTIVE_HOLD]
            for h in active:
                harness.outbid_hold(h)
            avail_before = quantize_usd(harness.wallet.available_balance)
            if avail_before < amount:
                with pytest.raises(DomainError) as exc_info:
                    apply_bid_lock(wallet=harness.wallet, amount=amount, now=now)
                assert exc_info.value.error_code == "INSUFFICIENT_AVAILABLE_BALANCE"
                assert quantize_usd(harness.wallet.available_balance) == avail_before
            else:
                harness.lock_bid(amount)

        elif step.kind == "OUTBID":
            active = [h for h in harness.holds if h.status == WalletHoldStatus.ACTIVE_HOLD]
            if active:
                harness.outbid_hold(active[0])

        elif step.kind == "SELF_OUTBID":
            active = [h for h in harness.holds if h.status == WalletHoldStatus.ACTIVE_HOLD]
            if active:
                harness.outbid_hold(active[0])
            avail_before = quantize_usd(harness.wallet.available_balance)
            if avail_before >= amount:
                harness.lock_bid(amount)
            else:
                with pytest.raises(DomainError) as exc_info:
                    apply_bid_lock(wallet=harness.wallet, amount=amount, now=now)
                assert exc_info.value.error_code == "INSUFFICIENT_AVAILABLE_BALANCE"

        elif step.kind == "MANUAL_CLAIM":
            claimable_list = [h for h in harness.holds if h.status == WalletHoldStatus.CLAIMABLE]
            if claimable_list:
                chosen = claimable_list[step.hold_selector % len(claimable_list)]
                harness.manual_claim(chosen)
                with pytest.raises(ConflictError) as dup_exc:
                    apply_manual_hold_claim(
                        wallet=harness.wallet,
                        hold=chosen,
                        requesting_user_id=harness.user_id,
                        now=now,
                    )
                assert dup_exc.value.status_code == 409
                assert dup_exc.value.error_code == "HOLD_ALREADY_CLAIMED"

        elif step.kind == "DUPLICATE_CLAIM":
            claimed_list = [h for h in harness.holds if h.status == WalletHoldStatus.CLAIMED]
            if claimed_list:
                chosen = claimed_list[step.hold_selector % len(claimed_list)]
                avail_before = quantize_usd(harness.wallet.available_balance)
                with pytest.raises(ConflictError) as dup_exc:
                    apply_manual_hold_claim(
                        wallet=harness.wallet,
                        hold=chosen,
                        requesting_user_id=harness.user_id,
                        now=now,
                    )
                assert dup_exc.value.status_code == 409
                assert dup_exc.value.error_code == "HOLD_ALREADY_CLAIMED"
                assert quantize_usd(harness.wallet.available_balance) == avail_before

        elif step.kind == "CLAIM_ALL":
            claimable_list = [h for h in harness.holds if h.status == WalletHoldStatus.CLAIMABLE]
            for h in claimable_list:
                harness.manual_claim(h)
            assert quantize_usd(harness.wallet.claimable_balance) == Decimal("0.00")

        harness.assert_invariants()


@settings(max_examples=100, deadline=None)
@given(
    initial_topup_cents=st.integers(min_value=10_000, max_value=500_000),
    first_bid_cents=st.integers(min_value=5_000, max_value=200_000),
    second_bid_cents=st.integers(min_value=5_000, max_value=400_000),
)
def test_rebidding_requires_full_available_balance_even_with_claimable_holds(
    initial_topup_cents: int,
    first_bid_cents: int,
    second_bid_cents: int,
) -> None:
    now = datetime(2026, 10, 26, 10, 0, 0, tzinfo=UTC)
    harness = WalletLedgerHarness(
        user_id=uuid.uuid4(),
        lot_id=uuid.uuid4(),
        now=now,
    )
    topup = quantize_usd(Decimal(initial_topup_cents) / Decimal("100"))
    first_bid = quantize_usd(Decimal(first_bid_cents) / Decimal("100"))
    second_bid = quantize_usd(Decimal(second_bid_cents) / Decimal("100"))

    harness.topup(topup)
    if first_bid > topup:
        with pytest.raises(DomainError) as exc_info:
            harness.lock_bid(first_bid)
        assert exc_info.value.error_code == "INSUFFICIENT_AVAILABLE_BALANCE"
        harness.assert_invariants()
        return

    first_hold = harness.lock_bid(first_bid)
    harness.outbid_hold(first_hold)

    remaining_avail = topup - first_bid
    assert quantize_usd(harness.wallet.available_balance) == remaining_avail
    assert quantize_usd(harness.wallet.claimable_balance) == first_bid

    if second_bid > remaining_avail:
        with pytest.raises(DomainError) as exc_info:
            harness.lock_bid(second_bid)
        assert exc_info.value.error_code == "INSUFFICIENT_AVAILABLE_BALANCE"
        assert exc_info.value.details["claimable_balance"] == str(first_bid)
        assert "claimable outbid holds" in exc_info.value.message
    else:
        second_hold = harness.lock_bid(second_bid)
        assert second_hold.status == WalletHoldStatus.ACTIVE_HOLD
        assert quantize_usd(harness.wallet.available_balance) == remaining_avail - second_bid
        assert quantize_usd(harness.wallet.held_balance) == second_bid
        assert quantize_usd(harness.wallet.claimable_balance) == first_bid

    harness.assert_invariants()
