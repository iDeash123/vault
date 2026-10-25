import React from "react";

export type BadgeTone =
  | "live"
  | "endingSoon"
  | "claimable"
  | "reserveMet"
  | "reserveUnmet"
  | "category"
  | "neutral";

export interface BadgeProps {
  tone: BadgeTone;
  children: React.ReactNode;
  className?: string | undefined;
}

const TONE_CLASSES: Record<BadgeTone, string> = {
  live: "bg-[#F5F5F5] text-[#141414] border-[#F5F5F5] font-semibold",
  endingSoon: "bg-[#141414] text-[#F5F5F5] border-[#F5F5F5] animate-pulse",
  claimable: "bg-[#D8D8D8] text-[#141414] border-[#F5F5F5] font-semibold",
  reserveMet: "bg-[#141414] text-[#F5F5F5] border-[#A6A6A6]",
  reserveUnmet: "bg-[#141414] text-[#A6A6A6] border-[#525252]",
  category: "bg-[#A6A6A6] text-[#141414] border-[#A6A6A6] font-semibold",
  neutral: "bg-[#141414] text-[#A6A6A6] border-[#262626]",
};

export const Badge: React.FC<BadgeProps> = ({
  tone,
  children,
  className = "",
}) => {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-none border px-2 py-0.5 text-[11px] font-mono-tech uppercase tracking-wider ${TONE_CLASSES[tone]} ${className}`}
    >
      {tone === "live" && <span className="w-1.5 h-1.5 bg-[#141414]" />}
      {children}
    </span>
  );
};
