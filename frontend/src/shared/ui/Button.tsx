import React from "react";

export type ButtonVariant = "primary" | "secondary" | "danger" | "ghost" | "buyNow";
export type ButtonSize = "sm" | "md" | "lg";

export interface ButtonProps {
  variant?: ButtonVariant | undefined;
  size?: ButtonSize | undefined;
  isLoading?: boolean | undefined;
  disabled?: boolean | undefined;
  fullWidth?: boolean | undefined;
  onClick?: (() => void) | undefined;
  type?: "button" | "submit" | undefined;
  children: React.ReactNode;
  className?: string | undefined;
}

const VARIANT_CLASSES: Record<ButtonVariant, string> = {
  primary:
    "bg-[#F5F5F5] text-[#141414] border-[#F5F5F5] hover:bg-[#D8D8D8] hover:border-[#D8D8D8]",
  secondary:
    "bg-[#141414] text-[#F5F5F5] border-[#262626] hover:border-[#F5F5F5] hover:bg-[#262626]",
  danger:
    "bg-[#141414] text-[#F5F5F5] border-[#F5F5F5] hover:bg-[#F5F5F5] hover:text-[#141414]",
  ghost:
    "bg-transparent text-[#A6A6A6] border-transparent hover:text-[#F5F5F5] hover:border-[#262626]",
  buyNow:
    "bg-[#A6A6A6] text-[#141414] border-[#F5F5F5] hover:bg-[#F5F5F5] font-bold",
};

const SIZE_CLASSES: Record<ButtonSize, string> = {
  sm: "px-3 py-1.5 text-xs",
  md: "px-4 py-2.5 text-xs",
  lg: "px-6 py-3.5 text-sm",
};

export const Button: React.FC<ButtonProps> = ({
  variant = "primary",
  size = "md",
  isLoading = false,
  disabled = false,
  fullWidth = false,
  onClick,
  type = "button",
  children,
  className = "",
}) => {
  const isDisabled = disabled || isLoading;
  return (
    <button
      type={type}
      disabled={isDisabled}
      onClick={onClick}
      className={`rounded-none border font-mono-tech uppercase tracking-wider transition-colors inline-flex items-center justify-center gap-2 ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${fullWidth ? "w-full" : ""} ${isDisabled ? "opacity-50 cursor-not-allowed" : "cursor-pointer"} ${className}`}
    >
      {isLoading ? (
        <span className="inline-flex items-center gap-2">
          <span className="w-2 h-2 bg-current animate-ping" />
          <span>PROCESSING...</span>
        </span>
      ) : (
        children
      )}
    </button>
  );
};
