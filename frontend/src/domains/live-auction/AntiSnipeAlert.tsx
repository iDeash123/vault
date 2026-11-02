import React from "react";
import { ReticleFrame } from "../../shared/ui/BrandGlyphs";

export interface AntiSnipeAlertProps {
  isExtended: boolean;
  extensionsCount: number;
  onDismiss?: (() => void) | undefined;
}

export const AntiSnipeAlert: React.FC<AntiSnipeAlertProps> = ({
  isExtended,
  extensionsCount,
  onDismiss,
}) => {
  if (!isExtended) {
    return null;
  }

  return (
    <div
      role="alert"
      data-testid="anti-snipe-alert"
      className="w-full rounded-none border border-[#F5F5F5] bg-[#F5F5F5] text-[#141414] px-4 py-3 font-mono-tech transition-all"
    >
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <ReticleFrame
            size="sm"
            bracketColor="#141414"
            className="px-2 py-0.5 text-xs font-bold uppercase tracking-wider bg-[#141414] text-[#F5F5F5]"
          >
            <span>ANTI-SNIPE TRIGGERED</span>
          </ReticleFrame>
          <div className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 text-xs uppercase tracking-wider font-bold">
            <span className="text-sm font-black">
              ANTI-SNIPE EXTENDED (+2:00)
            </span>
            <span className="text-[11px] font-normal text-[#525252]">
              [EXTENSION #{extensionsCount} · CLOCK RESET TO 120s]
            </span>
          </div>
        </div>

        {onDismiss !== undefined && (
          <button
            type="button"
            onClick={onDismiss}
            className="rounded-none border border-[#141414] bg-[#141414] text-[#F5F5F5] px-3 py-1 text-[11px] uppercase tracking-wider font-bold hover:bg-[#262626]"
          >
            DISMISS [X]
          </button>
        )}
      </div>
    </div>
  );
};
