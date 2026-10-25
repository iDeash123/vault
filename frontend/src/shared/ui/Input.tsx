import React, { useId } from "react";

export interface InputProps
  extends React.InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string | undefined;
  prefixText?: string | undefined;
  mono?: boolean | undefined;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  prefixText,
  mono = false,
  id,
  className = "",
  ...rest
}) => {
  const generatedId = useId();
  const inputId = id ?? generatedId;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      <label
        htmlFor={inputId}
        className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]"
      >
        {label}
      </label>
      <div className="flex items-stretch border border-[#262626] bg-[#141414] focus-within:border-[#F5F5F5]">
        {prefixText !== undefined && (
          <span className="px-3 py-2 text-xs font-mono-tech text-[#A6A6A6] border-r border-[#262626] flex items-center bg-[#141414]">
            {prefixText}
          </span>
        )}
        <input
          id={inputId}
          className={`w-full rounded-none bg-[#141414] px-3 py-2 text-sm text-[#F5F5F5] placeholder-[#525252] focus:outline-none ${mono ? "font-mono-tech" : "font-sans"} ${className}`}
          {...rest}
        />
      </div>
      {error !== undefined && error.length > 0 && (
        <span role="alert" className="text-xs font-mono-tech text-[#F5F5F5]">
          [ERROR] {error}
        </span>
      )}
    </div>
  );
};
