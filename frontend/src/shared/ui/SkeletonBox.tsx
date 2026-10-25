import React from "react";

export interface SkeletonBoxProps {
  className?: string | undefined;
  lines?: number | undefined;
}

export const SkeletonBox: React.FC<SkeletonBoxProps> = ({
  className = "h-24 w-full",
  lines = 1,
}) => {
  if (lines <= 1) {
    return (
      <div
        aria-busy="true"
        className={`rounded-none border border-[#262626] bg-[#262626]/50 animate-pulse ${className}`}
      />
    );
  }

  return (
    <div aria-busy="true" className="flex flex-col gap-2 w-full">
      {Array.from({ length: lines }).map((_, idx) => (
        <div
          key={idx}
          className={`rounded-none border border-[#262626] bg-[#262626]/50 animate-pulse ${className}`}
        />
      ))}
    </div>
  );
};
