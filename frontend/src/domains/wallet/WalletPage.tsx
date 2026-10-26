import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type {
  LedgerEntryItem,
  WalletHoldItem,
  WalletHoldStatus,
  WalletSummaryResponse,
} from "../../shared/types/domain";
import { Badge } from "../../shared/ui/Badge";
import { UnborderedWord } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Card } from "../../shared/ui/Card";
import { PriceTicker } from "../../shared/ui/PriceTicker";
import { SkeletonBox } from "../../shared/ui/SkeletonBox";
import { ClaimHoldButton, type ClaimHoldApiResponse } from "./ClaimHoldButton";
import { TopupModal } from "./TopupModal";

export interface ClaimAllApiResponse {
  claimed_count: number;
  claimed_amount: string;
  claimed_hold_ids: string[];
  available_balance: string;
  held_balance: string;
  claimable_balance: string;
  server_time: string;
}

function formatHoldStatusLabel(status: WalletHoldStatus): string {
  if (status === "CLAIMED") {
    return "RETURNED TO AVAILABLE";
  }
  if (status === "CAPTURED_TO_ESCROW") {
    return "CAPTURED TO ESCROW";
  }
  return "LEADING BID LOCKED";
}

export const WalletPage: React.FC = () => {
  const user = useAuthStore((state) => state.user);
  const storeClaimableCount = useAuthStore((state) => state.claimableCount);
  const updateBalances = useAuthStore((state) => state.updateBalances);
  const setClaimableCount = useAuthStore((state) => state.setClaimableCount);

  const [availableBalance, setAvailableBalance] = useState<string>(
    user?.available_balance ?? "0.00",
  );
  const [heldBalance, setHeldBalance] = useState<string>(
    user?.held_balance ?? "0.00",
  );
  const [claimableBalance, setClaimableBalance] = useState<string>(
    user?.claimable_balance ?? "0.00",
  );
  const [holds, setHolds] = useState<WalletHoldItem[]>([]);
  const [ledgerEntries, setLedgerEntries] = useState<LedgerEntryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isClaimingAll, setIsClaimingAll] = useState<boolean>(false);
  const [isTopupModalOpen, setIsTopupModalOpen] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>("");

  const syncStoreWithSummary = useCallback(
    (
      avail: string,
      held: string,
      claimable: string,
      currentHolds: WalletHoldItem[],
    ) => {
      updateBalances({
        available_balance: avail,
        held_balance: held,
        claimable_balance: claimable,
      });
      const count = currentHolds.filter((h) => h.status === "CLAIMABLE").length;
      setClaimableCount(count);
    },
    [setClaimableCount, updateBalances],
  );

  const loadWalletSummary = useCallback(async () => {
    if (
      useAuthStore.getState().user === null &&
      useAuthStore.getState().accessToken === null
    ) {
      setIsLoading(false);
      return;
    }
    setErrorMessage("");
    setIsLoading(true);
    try {
      const summary = await apiClient.get<WalletSummaryResponse>("/wallet");
      setAvailableBalance(summary.available_balance);
      setHeldBalance(summary.held_balance);
      setClaimableBalance(summary.claimable_balance);
      setHolds(summary.holds);
      setLedgerEntries(summary.ledger_entries);
      syncStoreWithSummary(
        summary.available_balance,
        summary.held_balance,
        summary.claimable_balance,
        summary.holds,
      );
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        if (err.status === 401) {
          useAuthStore.getState().clearSession();
        } else {
          setErrorMessage(err.message);
        }
      } else {
        setErrorMessage("Unable to load wallet summary.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [syncStoreWithSummary]);

  useEffect(() => {
    void loadWalletSummary();
  }, [loadWalletSummary]);

  useEffect(() => {
    if (user === null) {
      setAvailableBalance("0.00");
      setHeldBalance("0.00");
      setClaimableBalance("0.00");
      setHolds([]);
      setLedgerEntries([]);
      return;
    }
    if (isLoading) {
      return;
    }
    setAvailableBalance(user.available_balance);
    setHeldBalance(user.held_balance);
    setClaimableBalance(user.claimable_balance);
    if (Number(user.claimable_balance) === 0 && storeClaimableCount === 0) {
      setHolds((prevHolds) =>
        prevHolds.some((h) => h.status === "CLAIMABLE")
          ? prevHolds.map((item) =>
              item.status === "CLAIMABLE"
                ? { ...item, status: "CLAIMED" }
                : item,
            )
          : prevHolds,
      );
    }
  }, [
    isLoading,
    storeClaimableCount,
    user,
    user?.available_balance,
    user?.claimable_balance,
    user?.held_balance,
  ]);

  const handleSingleHoldClaimed = (response: ClaimHoldApiResponse) => {
    setErrorMessage("");
    setAvailableBalance(response.available_balance);
    setHeldBalance(response.held_balance);
    setClaimableBalance(response.claimable_balance);

    const remainingClaimable = holds.filter((h) =>
      h.id === response.hold.id
        ? response.hold.status === "CLAIMABLE"
        : h.status === "CLAIMABLE",
    ).length;
    setClaimableCount(remainingClaimable);

    setHolds((prevHolds) =>
      prevHolds.map((item) =>
        item.id === response.hold.id ? response.hold : item,
      ),
    );

    setLedgerEntries((prevEntries) => [
      {
        id: `claim-ledger-${response.hold.id}-${response.server_time}`,
        entry_type: "BID_MANUAL_CLAIM",
        amount: response.claimed_amount,
        available_delta: response.claimed_amount,
        held_delta: "0.00",
        claimable_delta: `-${response.claimed_amount}`,
        balance_available_after: response.available_balance,
        balance_held_after: response.held_balance,
        balance_claimable_after: response.claimable_balance,
        reference_lot_id: response.hold.lot_id,
        reference_hold_id: response.hold.id,
        created_at: response.server_time,
      },
      ...prevEntries,
    ]);
  };

  const handleClaimAll = async () => {
    setErrorMessage("");
    setIsClaimingAll(true);
    try {
      const response = await apiClient.post<ClaimAllApiResponse>(
        "/wallet/claims/claim-all",
      );
      setAvailableBalance(response.available_balance);
      setHeldBalance(response.held_balance);
      setClaimableBalance(response.claimable_balance);
      updateBalances({
        available_balance: response.available_balance,
        held_balance: response.held_balance,
        claimable_balance: response.claimable_balance,
      });
      setClaimableCount(0);

      const claimedSet = new Set(response.claimed_hold_ids);
      setHolds((prevHolds) =>
        prevHolds.map((item) =>
          claimedSet.has(item.id) || item.status === "CLAIMABLE"
            ? {
                ...item,
                status: "CLAIMED",
                claimed_at: response.server_time,
              }
            : item,
        ),
      );

      if (response.claimed_count > 0) {
        setLedgerEntries((prevEntries) => [
          {
            id: `claim-all-ledger-${response.server_time}`,
            entry_type: "BID_MANUAL_CLAIM",
            amount: response.claimed_amount,
            available_delta: response.claimed_amount,
            held_delta: "0.00",
            claimable_delta: `-${response.claimed_amount}`,
            balance_available_after: response.available_balance,
            balance_held_after: response.held_balance,
            balance_claimable_after: response.claimable_balance,
            reference_lot_id: null,
            reference_hold_id: null,
            created_at: response.server_time,
          },
          ...prevEntries,
        ]);
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Failed to claim all outbid holds.");
      }
    } finally {
      setIsClaimingAll(false);
    }
  };

  const claimableHolds = holds.filter((h) => h.status === "CLAIMABLE");

  if (user === null && !isLoading) {
    return (
      <div
        data-testid="wallet-unauthenticated"
        className="mx-auto max-w-xl py-12 flex flex-col gap-6"
      >
        <Card padding="lg" className="flex flex-col gap-4 text-center">
          <span className="text-xs font-mono-tech uppercase tracking-widest text-[#A6A6A6]">
            ARCHIVAL VAULT · ACCESS RESTRICTED
          </span>
          <h1 className="text-2xl font-display font-black uppercase text-[#F5F5F5]">
            AUTHENTICATION REQUIRED
          </h1>
          <p className="text-xs font-sans text-[#A6A6A6]">
            Sign in to access your three-bucket USD wallet, manage active bid
            holds, and claim outbid funds.
          </p>
          <div className="pt-2 flex justify-center">
            <Link
              to="/login"
              className="border border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] px-6 py-2.5 text-xs font-mono-tech font-bold uppercase hover:bg-[#D8D8D8]"
            >
              SIGN IN TO VAULT ↗
            </Link>
          </div>
        </Card>
      </div>
    );
  }

  return (
    <div data-testid="wallet-page" className="flex flex-col gap-8">
      <div className="border-b border-[#262626] pb-6 flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-mono-tech uppercase tracking-widest text-[#A6A6A6]">
            DOUBLE-ENTRY FINANCIAL CORE · SLICE 3.4
          </span>
          <h1 className="text-3xl md:text-4xl font-display font-black uppercase tracking-tight text-[#F5F5F5]">
            <UnborderedWord word="VAULT WALLET" cutoutColor="#141414" />
          </h1>
          <p className="text-xs font-sans text-[#A6A6A6] max-w-2xl">
            Outbid holds transition to Claimable Outbid Funds and never
            auto-refund to Available Balance without explicit manual claim.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            variant="primary"
            size="md"
            onClick={() => {
              setIsTopupModalOpen(true);
            }}
          >
            TOP UP VIA STRIPE
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="md"
            disabled={claimableHolds.length === 0}
            isLoading={isClaimingAll}
            onClick={() => {
              void handleClaimAll();
            }}
          >
            Claim All (${claimableBalance})
          </Button>
        </div>
      </div>

      {errorMessage.length > 0 && (
        <div
          role="alert"
          data-testid="wallet-error-banner"
          className="border border-[#F5F5F5] bg-[#141414] px-4 py-3 text-xs font-mono-tech text-[#F5F5F5]"
        >
          [WALLET_ERROR] {errorMessage}
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card padding="md" className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono-tech uppercase text-[#A6A6A6]">
              01 / AVAILABLE
            </span>
            <Badge tone="live">READY FOR BIDS</Badge>
          </div>
          <div data-testid="wallet-available-balance">
            <PriceTicker
              amountUsd={availableBalance}
              label="Available Balance"
              size="lg"
            />
          </div>
        </Card>

        <Card padding="md" className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono-tech uppercase text-[#A6A6A6]">
              02 / HELD
            </span>
            <Badge tone="neutral">LOCKED IN BIDS</Badge>
          </div>
          <div data-testid="wallet-held-balance">
            <PriceTicker
              amountUsd={heldBalance}
              label="Held in Active Bids"
              size="lg"
            />
          </div>
        </Card>

        <Card padding="md" className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono-tech uppercase text-[#A6A6A6]">
              03 / CLAIMABLE
            </span>
            <Badge tone="claimable">
              {String(claimableHolds.length)} OUTBID
            </Badge>
          </div>
          <div data-testid="wallet-claimable-balance">
            <PriceTicker
              amountUsd={claimableBalance}
              label="Claimable Outbid Funds"
              size="lg"
            />
          </div>
        </Card>
      </div>

      {isLoading ? (
        <div className="flex flex-col gap-3">
          <SkeletonBox className="h-16 w-full" />
          <SkeletonBox className="h-16 w-full" />
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card padding="md" className="flex flex-col gap-4">
            <div className="border-b border-[#262626] pb-3 flex items-center justify-between">
              <h2 className="text-sm font-mono-tech font-bold uppercase tracking-wider text-[#F5F5F5]">
                ACTIVE & CLAIMABLE HOLDS ({String(holds.length)})
              </h2>
              <span className="text-[11px] font-mono-tech text-[#525252]">
                MANUAL CLAIM PROTOCOL
              </span>
            </div>

            {holds.length === 0 ? (
              <p className="text-xs font-mono-tech text-[#525252] py-6 text-center">
                NO ACTIVE OR CLAIMABLE HOLDS RECORDED.
              </p>
            ) : (
              <div className="flex flex-col divide-y divide-[#262626]">
                {holds.map((hold) => (
                  <div
                    key={hold.id}
                    data-testid={`wallet-hold-row-${hold.id}`}
                    className="py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="flex flex-col gap-1">
                      <div className="flex items-center gap-2">
                        <Badge
                          tone={
                            hold.status === "CLAIMABLE"
                              ? "claimable"
                              : hold.status === "ACTIVE_HOLD"
                                ? "live"
                                : "neutral"
                          }
                        >
                          {hold.status}
                        </Badge>
                        <span className="text-xs font-mono-tech font-bold text-[#F5F5F5]">
                          ${hold.amount} USD
                        </span>
                      </div>
                      <span className="text-xs font-sans text-[#D8D8D8]">
                        {hold.lot_title}
                      </span>
                    </div>

                    {hold.status === "CLAIMABLE" ? (
                      <ClaimHoldButton
                        holdId={hold.id}
                        amountUsd={hold.amount}
                        onClaimSuccess={handleSingleHoldClaimed}
                        onClaimError={(msg) => {
                          setErrorMessage(msg);
                        }}
                      />
                    ) : (
                      <span className="text-[11px] font-mono-tech uppercase text-[#525252]">
                        {formatHoldStatusLabel(hold.status)}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Card>

          <Card padding="md" className="flex flex-col gap-4">
            <div className="border-b border-[#262626] pb-3 flex items-center justify-between">
              <h2 className="text-sm font-mono-tech font-bold uppercase tracking-wider text-[#F5F5F5]">
                LEDGER HISTORY ({String(ledgerEntries.length)})
              </h2>
              <span className="text-[11px] font-mono-tech text-[#525252]">
                IMMUTABLE AUDIT LOG
              </span>
            </div>

            {ledgerEntries.length === 0 ? (
              <p className="text-xs font-mono-tech text-[#525252] py-6 text-center">
                NO LEDGER ENTRIES RECORDED YET.
              </p>
            ) : (
              <div className="flex flex-col divide-y divide-[#262626]">
                {ledgerEntries.map((entry) => (
                  <div
                    key={entry.id}
                    data-testid={`ledger-entry-row-${entry.id}`}
                    className="py-3 flex flex-col gap-1.5 text-xs font-mono-tech"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-[#F5F5F5]">
                        {entry.entry_type}
                      </span>
                      <span className="text-[#D8D8D8]">
                        ${entry.amount} USD
                      </span>
                    </div>
                    <div className="flex flex-wrap gap-3 text-[11px] text-[#A6A6A6]">
                      <span>AVAIL Δ: {entry.available_delta}</span>
                      <span>HELD Δ: {entry.held_delta}</span>
                      <span>CLAIM Δ: {entry.claimable_delta}</span>
                    </div>
                    <div className="flex flex-wrap gap-3 text-[10px] text-[#525252]">
                      <span>AFTER AVAIL: ${entry.balance_available_after}</span>
                      <span>HELD: ${entry.balance_held_after}</span>
                      <span>CLAIMABLE: ${entry.balance_claimable_after}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Card>
        </div>
      )}

      <TopupModal
        isOpen={isTopupModalOpen}
        onClose={() => {
          setIsTopupModalOpen(false);
        }}
      />
    </div>
  );
};
