import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type { LotDetail } from "../../shared/types/domain";
import { ReticleFrame } from "../../shared/ui/BrandGlyphs";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";

export interface BidActionPanelProps {
  lot: LotDetail;
  onBidSuccess?: ((response: unknown) => void) | undefined;
  onBuyNowSuccess?: ((response: unknown) => void) | undefined;
}

function generateIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

export const BidActionPanel: React.FC<BidActionPanelProps> = ({
  lot,
  onBidSuccess,
  onBuyNowSuccess,
}) => {
  const user = useAuthStore((state) => state.user);
  const updateBalances = useAuthStore((state) => state.updateBalances);

  const [bidAmount, setBidAmount] = useState<string>(lot.min_valid_bid);
  const [isSubmittingBid, setIsSubmittingBid] = useState<boolean>(false);
  const [isSubmittingBuyNow, setIsSubmittingBuyNow] = useState<boolean>(false);
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [successMessage, setSuccessMessage] = useState<string>("");

  useEffect(() => {
    setBidAmount((prev) => {
      const prevNum = Number(prev);
      const minNum = Number(lot.min_valid_bid);
      if (Number.isNaN(prevNum) || prevNum < minNum) {
        return lot.min_valid_bid;
      }
      return prev;
    });
  }, [lot.min_valid_bid]);

  const isSeller = user !== null && user.id === lot.seller_id;
  const isLotLive = lot.status === "LIVE";
  const numericBid = Number(bidAmount);
  const numericMinBid = Number(lot.min_valid_bid);
  const numericAvail = user !== null ? Number(user.available_balance) : 0;

  const isBidValid =
    !Number.isNaN(numericBid) &&
    numericBid >= numericMinBid &&
    (!user || numericBid <= numericAvail);

  const handleQuickIncrement = (multiplier: number) => {
    const step = Number(lot.min_bid_increment) * multiplier;
    const currentVal = Number(bidAmount);
    const base =
      Number.isNaN(currentVal) || currentVal < numericMinBid
        ? numericMinBid
        : currentVal;
    const nextVal = (base + step).toFixed(2);
    setBidAmount(nextVal);
    setErrorMessage("");
  };

  const handlePlaceBid = async (e: React.SyntheticEvent) => {
    e.preventDefault();
    if (user === null) {
      setErrorMessage("Please authenticate to submit bids.");
      return;
    }
    if (isSeller) {
      setErrorMessage("Self-bidding is forbidden on your own lots.");
      return;
    }
    if (Number.isNaN(numericBid) || numericBid < numericMinBid) {
      setErrorMessage(`Bid must be at least $${lot.min_valid_bid}`);
      return;
    }
    if (numericBid > numericAvail) {
      setErrorMessage("Insufficient available balance to lock 100% of bid amount.");
      return;
    }

    setErrorMessage("");
    setSuccessMessage("");
    setIsSubmittingBid(true);

    try {
      const idempotencyKey = generateIdempotencyKey();
      const response = await apiClient.post(
        `/lots/${lot.id}/bids`,
        { amount: numericBid.toFixed(2) },
        {
          "Idempotency-Key": idempotencyKey,
        },
      );

      const latestUser = useAuthStore.getState().user;
      if (latestUser !== null) {
        const latestAvail = Number(latestUser.available_balance);
        const latestHeld = Number(latestUser.held_balance);
        const nextAvail = (
          Number.isNaN(latestAvail) ? 0 : Math.max(0, latestAvail - numericBid)
        ).toFixed(2);
        const nextHeld = (
          Number.isNaN(latestHeld) ? numericBid : latestHeld + numericBid
        ).toFixed(2);
        updateBalances({
          available_balance: nextAvail,
          held_balance: nextHeld,
        });
      }

      setSuccessMessage(`Bid of $${numericBid.toFixed(2)} placed successfully.`);
      onBidSuccess?.(response);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Failed to place bid.");
      }
    } finally {
      setIsSubmittingBid(false);
    }
  };

  const handleBuyNow = async () => {
    if (user === null) {
      setErrorMessage("Please authenticate to execute instant buy-now.");
      return;
    }
    if (isSeller) {
      setErrorMessage("Self-bidding/instant buy-now forbidden on own lots.");
      return;
    }
    if (lot.buy_now_price === null) {
      setErrorMessage("Buy now price is not configured for this lot.");
      return;
    }
    const buyPrice = Number(lot.buy_now_price);
    if (buyPrice > numericAvail) {
      setErrorMessage("Insufficient available balance for instant buy-now.");
      return;
    }

    setErrorMessage("");
    setSuccessMessage("");
    setIsSubmittingBuyNow(true);

    try {
      const idempotencyKey = generateIdempotencyKey();
      const response = await apiClient.post(
        `/lots/${lot.id}/buy-now`,
        {},
        {
          "Idempotency-Key": idempotencyKey,
        },
      );

      const latestUser = useAuthStore.getState().user;
      if (latestUser !== null) {
        const latestAvail = Number(latestUser.available_balance);
        const latestHeld = Number(latestUser.held_balance);
        const nextAvail = (
          Number.isNaN(latestAvail) ? 0 : Math.max(0, latestAvail - buyPrice)
        ).toFixed(2);
        const nextHeld = (
          Number.isNaN(latestHeld) ? buyPrice : latestHeld + buyPrice
        ).toFixed(2);
        updateBalances({
          available_balance: nextAvail,
          held_balance: nextHeld,
        });
      }

      setSuccessMessage("Instant Buy-Now executed. Escrow order created.");
      onBuyNowSuccess?.(response);
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Buy now execution failed.");
      }
    } finally {
      setIsSubmittingBuyNow(false);
    }
  };

  return (
    <div
      data-testid="bid-action-panel"
      className="rounded-none border border-[#262626] bg-[#141414] p-4 flex flex-col gap-4 font-mono-tech"
    >
      <div className="flex items-center justify-between border-b border-[#262626] pb-3 text-xs uppercase tracking-wider">
        <span className="text-[#A6A6A6]">BIDDING TERMINAL</span>
        <span className="text-[#F5F5F5] font-bold">
          MIN STEP: +${lot.min_bid_increment}
        </span>
      </div>

      {isSeller && (
        <div
          role="status"
          data-testid="seller-notice"
          className="border border-[#262626] bg-[#262626]/40 p-2.5 text-xs text-[#A6A6A6] uppercase tracking-wider"
        >
          YOU ARE THE SELLER OF THIS ARCHIVAL LOT · BIDDING DISABLED
        </div>
      )}

      {!isLotLive && (
        <div
          role="status"
          data-testid="status-notice"
          className="border border-[#262626] bg-[#262626]/40 p-2.5 text-xs text-[#A6A6A6] uppercase tracking-wider"
        >
          AUCTION STATUS: {lot.status} · BIDDING CLOSED
        </div>
      )}

      {user === null && (
        <div className="border border-[#262626] p-3 text-xs flex items-center justify-between">
          <span className="text-[#A6A6A6] uppercase">
            AUTHENTICATION REQUIRED TO BID
          </span>
          <Link
            to="/login"
            className="border border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] px-3 py-1 text-xs font-bold uppercase"
          >
            LOGIN ↗
          </Link>
        </div>
      )}

      {user !== null && (
        <div className="flex items-center justify-between text-xs border border-[#262626] px-3 py-2 bg-[#141414]">
          <span className="text-[#A6A6A6] uppercase">AVAILABLE BALANCE</span>
          <span className="font-bold text-[#F5F5F5]">
            ${user.available_balance} USD
          </span>
        </div>
      )}

      <form
        onSubmit={(e) => {
          void handlePlaceBid(e);
        }}
        className="flex flex-col gap-3"
      >
        <div>
          <div className="flex items-center justify-between text-xs mb-1">
            <span className="text-[#A6A6A6] uppercase">NEXT MINIMUM BID</span>
            <span className="font-bold text-[#F5F5F5]">
              ${lot.min_valid_bid} USD
            </span>
          </div>
          <Input
            label="BID AMOUNT (USD)"
            type="number"
            step="0.01"
            min={lot.min_valid_bid}
            prefixText="$"
            mono
            value={bidAmount}
            onChange={(e) => {
              setBidAmount(e.target.value);
              setErrorMessage("");
            }}
            disabled={!isLotLive || isSeller || isSubmittingBid}
            placeholder={lot.min_valid_bid}
          />
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={!isLotLive || isSeller}
            onClick={() => {
              handleQuickIncrement(1);
            }}
            className="flex-1 rounded-none border border-[#262626] bg-[#141414] py-1 text-xs text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5] uppercase disabled:opacity-40"
          >
            +${lot.min_bid_increment}
          </button>
          <button
            type="button"
            disabled={!isLotLive || isSeller}
            onClick={() => {
              handleQuickIncrement(2);
            }}
            className="flex-1 rounded-none border border-[#262626] bg-[#141414] py-1 text-xs text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5] uppercase disabled:opacity-40"
          >
            +${(Number(lot.min_bid_increment) * 2).toFixed(2)}
          </button>
          <button
            type="button"
            disabled={!isLotLive || isSeller}
            onClick={() => {
              handleQuickIncrement(5);
            }}
            className="flex-1 rounded-none border border-[#262626] bg-[#141414] py-1 text-xs text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5] uppercase disabled:opacity-40"
          >
            +${(Number(lot.min_bid_increment) * 5).toFixed(2)}
          </button>
        </div>

        <div data-testid="place-bid-button">
          <Button
            type="submit"
            variant="primary"
            size="md"
            fullWidth
            isLoading={isSubmittingBid}
            disabled={!isLotLive || isSeller || !isBidValid || isSubmittingBid}
          >
            PLACE BID (${Number.isNaN(numericBid) ? "0.00" : numericBid.toFixed(2)})
          </Button>
        </div>
      </form>

      {lot.is_buy_now_available && lot.buy_now_price !== null && (
        <div className="border-t border-[#262626] pt-3 flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs">
            <span className="text-[#A6A6A6] uppercase">INSTANT ESCROW CAPTURE</span>
            <ReticleFrame
              size="sm"
              bracketColor="#F5F5F5"
              className="px-1.5 py-0.5 text-[10px] font-bold uppercase text-[#F5F5F5]"
            >
              <span>BLITZ</span>
            </ReticleFrame>
          </div>
          <div data-testid="buy-now-button">
            <Button
              type="button"
              variant="secondary"
              size="md"
              fullWidth
              isLoading={isSubmittingBuyNow}
              disabled={!isLotLive || isSeller || isSubmittingBuyNow}
              onClick={() => {
                void handleBuyNow();
              }}
            >
              BUY NOW (${lot.buy_now_price})
            </Button>
          </div>
        </div>
      )}

      {errorMessage.length > 0 && (
        <div
          role="alert"
          data-testid="bid-panel-error"
          className="border border-[#262626] bg-[#141414] p-2 text-xs text-[#F5F5F5] uppercase tracking-wider"
        >
          [ERROR] {errorMessage}
        </div>
      )}

      {successMessage.length > 0 && (
        <div
          role="status"
          data-testid="bid-panel-success"
          className="border border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] p-2 text-xs font-bold uppercase tracking-wider"
        >
          [CONFIRMED] {successMessage}
        </div>
      )}
    </div>
  );
};
