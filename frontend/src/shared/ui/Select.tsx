import React, { useId } from "react";

export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  label: string;
  options: ReadonlyArray<SelectOption>;
  value: string;
  onChange: (val: string) => void;
  error?: string | undefined;
  disabled?: boolean | undefined;
  id?: string | undefined;
}

export const Select: React.FC<SelectProps> = ({
  label,
  options,
  value,
  onChange,
  error,
  disabled = false,
  id,
}) => {
  const generatedId = useId();
  const selectId = id ?? generatedId;

  return (
    <div className="flex flex-col gap-1.5 w-full">
      <label
        htmlFor={selectId}
        className="text-xs font-mono-tech uppercase tracking-wider text-[#A6A6A6]"
      >
        {label}
      </label>
      <select
        id={selectId}
        value={value}
        disabled={disabled}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        className="w-full rounded-none border border-[#262626] bg-[#141414] px-3 py-2 text-xs font-mono-tech uppercase tracking-wider text-[#F5F5F5] focus:border-[#F5F5F5] focus:outline-none"
      >
        {options.map((opt) => (
          <option
            key={opt.value}
            value={opt.value}
            className="bg-[#141414] text-[#F5F5F5]"
          >
            {opt.label}
          </option>
        ))}
      </select>
      {error !== undefined && error.length > 0 && (
        <span role="alert" className="text-xs font-mono-tech text-[#F5F5F5]">
          [ERROR] {error}
        </span>
      )}
    </div>
  );
};
