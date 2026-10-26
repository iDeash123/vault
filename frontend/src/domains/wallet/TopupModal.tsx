import React, { useEffect, useState } from "react";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { Button } from "../../shared/ui/Button";
import { Input } from "../../shared/ui/Input";
import { Modal } from "../../shared/ui/Modal";

export interface TopupCheckoutSessionResponse {
  checkout_url: string;
  session_id: string;
  server_time: string;
}

export interface TopupModalProps {
  isOpen: boolean;
  onClose: () => void;
  onCheckoutCreated?:
    | ((session: TopupCheckoutSessionResponse) => void)
    | undefined;
}

const PRESET_AMOUNTS: ReadonlyArray<string> = [
  "250.00",
  "500.00",
  "1000.00",
  "2500.00",
];

const USD_AMOUNT_PATTERN = /^\d+(\.\d{1,2})?$/;

export const TopupModal: React.FC<TopupModalProps> = ({
  isOpen,
  onClose,
  onCheckoutCreated,
}) => {
  const [amountUsd, setAmountUsd] = useState<string>("500.00");
  const [errorMessage, setErrorMessage] = useState<string>("");
  const [isCreatingSession, setIsCreatingSession] = useState<boolean>(false);
  const [createdSession, setCreatedSession] =
    useState<TopupCheckoutSessionResponse | null>(null);

  useEffect(() => {
    if (!isOpen) {
      setErrorMessage("");
      setCreatedSession(null);
    }
  }, [isOpen]);

  const handleClose = () => {
    setErrorMessage("");
    setCreatedSession(null);
    onClose();
  };

  const handleCheckoutSubmit = async () => {
    setErrorMessage("");
    const trimmed = amountUsd.trim();
    const numeric = Number(trimmed);
    if (
      !USD_AMOUNT_PATTERN.test(trimmed) ||
      !Number.isFinite(numeric) ||
      numeric < 0.01 ||
      numeric > 1_000_000
    ) {
      setErrorMessage(
        "Enter a valid USD amount between $0.01 and $1,000,000.00 (up to 2 decimal places).",
      );
      return;
    }

    const formatted = numeric.toFixed(2);
    setIsCreatingSession(true);
    try {
      const response = await apiClient.post<TopupCheckoutSessionResponse>(
        "/wallet/topup/checkout",
        {
          amount_usd: formatted,
        },
      );
      setCreatedSession(response);
      if (onCheckoutCreated !== undefined) {
        onCheckoutCreated(response);
      } else if (import.meta.env.MODE !== "test") {
        window.location.assign(response.checkout_url);
      }
    } catch (err: unknown) {
      if (err instanceof ApiClientError) {
        setErrorMessage(err.message);
      } else {
        setErrorMessage("Unable to initialize Stripe Checkout session.");
      }
    } finally {
      setIsCreatingSession(false);
    }
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={handleClose}
      title="STRIPE VAULT TOP-UP"
      footer={
        <>
          <Button variant="secondary" size="sm" onClick={handleClose}>
            CANCEL
          </Button>
          <Button
            variant="primary"
            size="sm"
            isLoading={isCreatingSession}
            onClick={() => {
              void handleCheckoutSubmit();
            }}
          >
            PROCEED TO STRIPE CHECKOUT
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <p className="text-xs font-sans text-[#A6A6A6]">
          Funds are credited to your Available Balance upon verified Stripe
          Webhook confirmation (idempotent double-entry ledger).
        </p>

        <div className="grid grid-cols-4 gap-2">
          {PRESET_AMOUNTS.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => {
                setAmountUsd(preset);
                setErrorMessage("");
              }}
              className={`rounded-none border px-2 py-2 text-xs font-mono-tech uppercase ${
                amountUsd === preset
                  ? "border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] font-bold"
                  : "border-[#262626] bg-[#141414] text-[#D8D8D8] hover:border-[#F5F5F5]"
              }`}
            >
              ${preset}
            </button>
          ))}
        </div>

        <Input
          label="TOP-UP AMOUNT (USD)"
          type="text"
          prefixText="$"
          mono
          value={amountUsd}
          error={errorMessage.length > 0 ? errorMessage : undefined}
          onChange={(e) => {
            setAmountUsd(e.target.value);
            setErrorMessage("");
          }}
        />

        {createdSession !== null && (
          <div
            data-testid="stripe-checkout-session-banner"
            className="border border-[#F5F5F5] bg-[#141414] p-3 text-xs font-mono-tech text-[#F5F5F5]"
          >
            SESSION READY ({createdSession.session_id}):{" "}
            <a
              href={createdSession.checkout_url}
              className="underline text-[#D8D8D8]"
            >
              OPEN STRIPE CHECKOUT ↗
            </a>
          </div>
        )}
      </div>
    </Modal>
  );
};
