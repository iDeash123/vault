import React from "react";
import { ReticleFrame } from "./BrandGlyphs";
import { Button } from "./Button";

export interface ClaimableHoldsBannerProps {
  claimableBalance: string;
  claimableCount: number;
  onClaimAll: () => Promise<void> | void;
  isClaiming: boolean;
}

export const ClaimableHoldsBanner: React.FC<ClaimableHoldsBannerProps> = ({
  claimableBalance,
  claimableCount,
  onClaimAll,
  isClaiming,
}) => {
  const numericBalance = Number(claimableBalance);
  if (claimableCount <= 0 && (Number.isNaN(numericBalance) || numericBalance <= 0)) {
    return null;
  }

  return (
    <div
      role="region"
      aria-label="Claimable Outbid Holds Banner"
      data-testid="claimable-holds-banner"
      className="w-full rounded-none border-b border-[#262626] bg-[#D8D8D8] px-4 py-3 text-[#141414]"
    >
      <div className="mx-auto flex max-w-[1360px] flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <ReticleFrame
            size="sm"
            bracketColor="#141414"
            className="px-2 py-0.5 text-[11px] font-mono-tech font-bold uppercase"
          >
            <span>CLAIMABLE</span>
          </ReticleFrame>
          <p className="text-xs font-mono-tech uppercase tracking-wider">
            YOU HAVE{" "}
            <strong className="font-bold">${claimableBalance} USD</strong> ACROSS{" "}
            <strong className="font-bold">{claimableCount}</strong> OUTBID{" "}
            {claimableCount === 1 ? "HOLD" : "HOLDS"} READY FOR MANUAL CLAIM TO
            AVAILABLE BALANCE.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          isLoading={isClaiming}
          onClick={() => {
            void onClaimAll();
          }}
        >
          CLAIM ALL (${claimableBalance})
        </Button>
      </div>
    </div>
  );
};
