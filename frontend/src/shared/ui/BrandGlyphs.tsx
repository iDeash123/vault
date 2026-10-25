import React from "react";

export interface SlashedZeroGlyphProps {
  className?: string | undefined;
  strokeColor?: string | undefined;
  checkColor?: string | undefined;
}

export const SlashedZeroGlyph: React.FC<SlashedZeroGlyphProps> = ({
  className = "w-16 h-20",
  strokeColor = "currentColor",
  checkColor = "#141414",
}) => {
  return (
    <svg
      viewBox="0 0 100 120"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="Slashed O Glyph"
    >
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M50 8C23.5 8 6 30 6 60C6 90 23.5 112 50 112C76.5 112 94 90 94 60C94 30 76.5 8 50 8ZM50 24C66.5 24 77 40 77 60C77 80 66.5 96 50 96C33.5 96 23 80 23 60C23 40 33.5 24 50 24Z"
        fill={strokeColor}
      />
      <polygon points="72,6 88,6 28,114 12,114" fill={strokeColor} />
      <rect x="61" y="12" width="9" height="9" fill={checkColor} />
      <rect x="70" y="21" width="9" height="9" fill={checkColor} />
      <rect x="52" y="21" width="9" height="9" fill={strokeColor} />
      <rect x="21" y="90" width="9" height="9" fill={checkColor} />
      <rect x="30" y="99" width="9" height="9" fill={checkColor} />
      <rect x="30" y="81" width="9" height="9" fill={strokeColor} />
    </svg>
  );
};

export interface ReticleFrameProps {
  children?: React.ReactNode | undefined;
  className?: string | undefined;
  bracketColor?: string | undefined;
  size?: "sm" | "md" | "lg" | undefined;
}

export const ReticleFrame: React.FC<ReticleFrameProps> = ({
  children,
  className = "",
  bracketColor = "currentColor",
  size = "md",
}) => {
  const dim = size === "sm" ? 7 : size === "lg" ? 14 : 10;
  return (
    <div className={`relative inline-flex items-center justify-center ${className}`}>
      <svg
        width={dim}
        height={dim}
        viewBox="0 0 12 12"
        className="absolute top-0 left-0 pointer-events-none"
        style={{ color: bracketColor }}
      >
        <polygon points="0,0 11,0 7,3 3,3 3,7 0,11" fill="currentColor" />
      </svg>
      <svg
        width={dim}
        height={dim}
        viewBox="0 0 12 12"
        className="absolute top-0 right-0 pointer-events-none"
        style={{ color: bracketColor }}
      >
        <polygon points="12,0 1,0 5,3 9,3 9,7 12,11" fill="currentColor" />
      </svg>
      <svg
        width={dim}
        height={dim}
        viewBox="0 0 12 12"
        className="absolute bottom-0 left-0 pointer-events-none"
        style={{ color: bracketColor }}
      >
        <polygon points="0,12 11,12 7,9 3,9 3,5 0,1" fill="currentColor" />
      </svg>
      <svg
        width={dim}
        height={dim}
        viewBox="0 0 12 12"
        className="absolute bottom-0 right-0 pointer-events-none"
        style={{ color: bracketColor }}
      >
        <polygon points="12,12 1,12 5,9 9,9 9,5 12,1" fill="currentColor" />
      </svg>
      {children}
    </div>
  );
};

export interface UnborderedWordProps {
  word: string;
  className?: string | undefined;
  cutoutColor?: string | undefined;
}

export const UnborderedWord: React.FC<UnborderedWordProps> = ({
  word,
  className = "",
  cutoutColor = "#141414",
}) => {
  const parts = word.split("Ø");
  if (parts.length === 1) {
    return <span className={className}>{word}</span>;
  }
  return (
    <span className={`inline-flex items-baseline ${className}`}>
      {parts.map((part, idx) => (
        <React.Fragment key={idx}>
          <span>{part}</span>
          {idx < parts.length - 1 && (
            <span className="inline-block relative mx-[-0.02em] self-center">
              <SlashedZeroGlyph
                className="h-[0.76em] w-[0.65em] translate-y-[0.06em]"
                strokeColor="currentColor"
                checkColor={cutoutColor}
              />
            </span>
          )}
        </React.Fragment>
      ))}
    </span>
  );
};
