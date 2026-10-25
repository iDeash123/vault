import React, { useEffect, useRef, useState } from "react";
import { getRemainingMs, useClockStore } from "../store/clockStore";
import type { LotStatus } from "../types/domain";
import { ReticleFrame } from "./BrandGlyphs";

export interface CountdownTimerProps {
  endsAtIso: string;
  status: LotStatus;
  antiSnipeExtensionsCount: number;
  onExpire?: (() => void) | undefined;
}

const ANTI_SNIPE_THRESHOLD_MS = 120_000;

function formatDurationMs(ms: number): string {
  const totalSeconds = Math.ceil(ms / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  const hh = String(hours).padStart(2, "0");
  const mm = String(minutes).padStart(2, "0");
  const ss = String(seconds).padStart(2, "0");
  return `${hh}:${mm}:${ss}`;
}

export const CountdownTimer: React.FC<CountdownTimerProps> = ({
  endsAtIso,
  status,
  antiSnipeExtensionsCount,
  onExpire,
}) => {
  const clockOffsetMs = useClockStore((state) => state.clockOffsetMs);
  const [remainingMs, setRemainingMs] = useState<number>(() =>
    getRemainingMs(endsAtIso),
  );
  const expiredNotifiedRef = useRef<boolean>(false);

  useEffect(() => {
    expiredNotifiedRef.current = false;
    const updateTimer = () => {
      const nextRemaining = getRemainingMs(endsAtIso);
      setRemainingMs(nextRemaining);
      if (nextRemaining === 0 && !expiredNotifiedRef.current) {
        expiredNotifiedRef.current = true;
        onExpire?.();
      }
    };

    updateTimer();
    const intervalId = window.setInterval(updateTimer, 250);
    return () => {
      window.clearInterval(intervalId);
    };
  }, [endsAtIso, clockOffsetMs, onExpire]);

  const isLive = status === "LIVE";
  const isAntiSnipeZone =
    isLive && remainingMs > 0 && remainingMs < ANTI_SNIPE_THRESHOLD_MS;

  return (
    <div
      data-testid="countdown-timer"
      data-anti-snipe={isAntiSnipeZone ? "true" : "false"}
      className={`rounded-none border px-3 py-2 font-mono-tech ${
        isAntiSnipeZone
          ? "border-[#F5F5F5] bg-[#F5F5F5] text-[#141414]"
          : "border-[#262626] bg-[#141414] text-[#F5F5F5]"
      }`}
    >
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-bold tracking-wider">
          {isLive && remainingMs > 0
            ? formatDurationMs(remainingMs)
            : remainingMs === 0 && isLive
              ? "00:00:00"
              : status}
        </span>
        {isAntiSnipeZone && (
          <ReticleFrame
            size="sm"
            bracketColor="#141414"
            className="px-2 py-0.5 text-[10px] font-bold uppercase tracking-widest"
          >
            <span>ANTI-SNIPE ZONE</span>
          </ReticleFrame>
        )}
      </div>
      {antiSnipeExtensionsCount > 0 && (
        <div className="mt-1 text-[10px] uppercase tracking-wider opacity-85">
          +2:00 EXTENDED x{antiSnipeExtensionsCount}
        </div>
      )}
    </div>
  );
};
