import React from "react";
import { ReticleFrame } from "./BrandGlyphs";

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  footer?: React.ReactNode | undefined;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  footer,
}) => {
  if (!isOpen) {
    return null;
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label={title}
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#141414]/85 p-4"
    >
      <ReticleFrame
        size="lg"
        bracketColor="#F5F5F5"
        className="w-full max-w-lg bg-[#141414] border border-[#262626] p-6"
      >
        <div className="w-full flex flex-col gap-5">
          <div className="flex items-center justify-between border-b border-[#262626] pb-3">
            <h2 className="text-lg font-display font-bold uppercase tracking-tight text-[#F5F5F5]">
              {title}
            </h2>
            <button
              type="button"
              onClick={onClose}
              aria-label="Close modal"
              className="rounded-none border border-[#262626] px-2.5 py-1 text-xs font-mono-tech uppercase text-[#A6A6A6] hover:border-[#F5F5F5] hover:text-[#F5F5F5]"
            >
              [X]
            </button>
          </div>
          <div className="text-sm text-[#D8D8D8]">{children}</div>
          {footer !== undefined && (
            <div className="border-t border-[#262626] pt-4 flex items-center justify-end gap-3">
              {footer}
            </div>
          )}
        </div>
      </ReticleFrame>
    </div>
  );
};
