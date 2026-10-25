import React from "react";

export type CardPadding = "none" | "sm" | "md" | "lg";

export interface CardProps {
  padding?: CardPadding | undefined;
  interactive?: boolean | undefined;
  children: React.ReactNode;
  className?: string | undefined;
  onClick?: (() => void) | undefined;
}

const PADDING_CLASSES: Record<CardPadding, string> = {
  none: "p-0",
  sm: "p-3",
  md: "p-5",
  lg: "p-8",
};

export const Card: React.FC<CardProps> = ({
  padding = "md",
  interactive = false,
  children,
  className = "",
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`rounded-none border border-[#262626] bg-[#141414] text-[#F5F5F5] ${PADDING_CLASSES[padding]} ${interactive ? "hover:border-[#F5F5F5] transition-colors cursor-pointer" : ""} ${className}`}
    >
      {children}
    </div>
  );
};
