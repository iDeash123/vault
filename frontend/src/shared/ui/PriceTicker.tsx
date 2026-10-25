import React, { useEffect, useState } from "react";

export type PriceTickerSize = "sm" | "md" | "lg" | "hero";

export interface PriceTickerProps {
  amountUsd: string;
  label: string;
  size?: PriceTickerSize | undefined;
  highlightChange?: boolean | undefined;
}

const SIZE_CLASSES: Record<PriceTickerSize, string> = {
  sm: "text-base",
  md: "text-xl",
  lg: "text-3xl",
  hero: "text-4xl md:text-5xl",
};

function formatUsdDisplay(amountUsd: string): string {
  const numeric = Number(amountUsd);
  if (Number.isNaN(numeric)) {
    return `$${amountUsd}`;
  }
  return `$${numeric.toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;
}

export const PriceTicker: React.FC<PriceTickerProps> = ({
  amountUsd,
  label,
  size = "md",
  highlightChange = false,
}) => {
  const [isFlashing, setIsFlashing] = useState<boolean>(highlightChange);

  useEffect(() => {
    setIsFlashing(true);
    const timerId = window.setTimeout(() => {
      setIsFlashing(false);
    }, 450);
    return () => {
      window.clearTimeout(timerId);
    };
  }, [amountUsd, highlightChange]);

  return (
    <div
      data-testid="price-ticker"
      className={`rounded-none border px-3 py-2 transition-colors ${
        isFlashing
          ? "border-[#F5F5F5] bg-[#F5F5F5] text-[#141414]"
          : "border-[#262626] bg-[#141414] text-[#F5F5F5]"
      }`}
    >
      <div className="text-[10px] font-mono-tech uppercase tracking-widest opacity-75">
        {label}
      </div>
      <div
        className={`font-mono-tech font-bold tracking-tight ${SIZE_CLASSES[size]}`}
      >
        {formatUsdDisplay(amountUsd)}
      </div>
    </div>
  );
};
