import React from "react";
import { ReticleFrame } from "./BrandGlyphs";

export type ToastType =
  | "OUTBID"
  | "LOT_EXTENDED"
  | "HOLD_BECAME_CLAIMABLE"
  | "INFO"
  | "ERROR";

export interface ToastProps {
  id: string;
  type: ToastType;
  title: string;
  message: string;
  onDismiss: (id: string) => void;
}

export const Toast: React.FC<ToastProps> = ({
  id,
  type,
  title,
  message,
  onDismiss,
}) => {
  return (
    <ReticleFrame
      size="sm"
      bracketColor="#F5F5F5"
      className="w-full max-w-sm border border-[#262626] bg-[#141414] p-3 text-[#F5F5F5]"
    >
      <div role="status" className="w-full flex flex-col gap-1">
        <div className="flex items-center justify-between gap-2 border-b border-[#262626] pb-1.5">
          <span className="text-[10px] font-mono-tech uppercase tracking-widest text-[#A6A6A6]">
            [{type}] {title}
          </span>
          <button
            type="button"
            onClick={() => {
              onDismiss(id);
            }}
            aria-label="Dismiss notification"
            className="text-[10px] font-mono-tech uppercase text-[#A6A6A6] hover:text-[#F5F5F5]"
          >
            [X]
          </button>
        </div>
        <p className="pt-1 text-xs font-mono-tech text-[#D8D8D8]">{message}</p>
      </div>
    </ReticleFrame>
  );
};
