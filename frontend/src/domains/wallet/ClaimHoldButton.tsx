import React, { useState } from "react";
import { ApiClientError, apiClient } from "../../shared/api/client";
import { useAuthStore } from "../../shared/store/authStore";
import type { WalletHoldItem } from "../../shared/types/domain";
import { Button } from "../../shared/ui/Button";

export interface ClaimHoldApiResponse {
  hold: WalletHoldItem;
  claimed_amount: string;
  available_balance: string;
  held_balance: string;
  claimable_balance: string;
  server_time: string;
}

export interface ClaimHoldButtonProps {
  holdId: string;
  amountUsd: string;
  disabled?: boolean | undefined;
  onClaimSuccess?: ((response: ClaimHoldApiResponse) => void) | undefined;
  onClaimError?: ((errorMessage: string) => void) | undefined;
}

export const ClaimHoldButton: React.FC<ClaimHoldButtonProps> = ({
  holdId,
  amountUsd,
  disabled = false,
  onClaimSuccess,
  onClaimError,
}) => {
  const [isClaiming, setIsClaiming] = useState<boolean>(false);
  const updateBalances = useAuthStore((state) => state.updateBalances);

  const handleClaim = async () => {
    setIsClaiming(true);
    try {
      const response = await apiClient.post<ClaimHoldApiResponse>(
        `/wallet/claims/${holdId}`,
      );
      updateBalances({
        available_balance: response.available_balance,
        held_balance: response.held_balance,
        claimable_balance: response.claimable_balance,
      });
      if (onClaimSuccess !== undefined) {
        onClaimSuccess(response);
      }
    } catch (err: unknown) {
      if (onClaimError !== undefined) {
        if (err instanceof ApiClientError) {
          onClaimError(err.message);
        } else {
          onClaimError("Failed to claim outbid hold.");
        }
      }
    } finally {
      setIsClaiming(false);
    }
  };

  return (
    <Button
      type="button"
      variant="primary"
      size="sm"
      disabled={disabled}
      isLoading={isClaiming}
      onClick={() => {
        void handleClaim();
      }}
    >
      Claim Bid (${amountUsd})
    </Button>
  );
};
