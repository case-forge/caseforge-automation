"use client";

import { useRef, type InputHTMLAttributes } from "react";
import { IconClose } from "./icons";

type Props = Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "value" | "onChange"> & {
  value: string;
  onValueChange: (value: string) => void;

  clearLabel: string;
  wrapClassName?: string;
};

export function SearchClearButton({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <button type="button" className="cf-btn cf-btn--icon cf-btn--compact search-clear" aria-label={label} title={label} onClick={onClear}>
      <IconClose aria-hidden="true" />
    </button>
  );
}

export function ClearableSearch({ value, onValueChange, clearLabel, wrapClassName, ...input }: Props) {
  const ref = useRef<HTMLInputElement>(null);
  return (
    <span className={`clearable-search${wrapClassName ? ` ${wrapClassName}` : ""}`}>
      <input {...input} ref={ref} type="search" value={value} onChange={(e) => onValueChange(e.target.value)} />
      {value !== "" && (
        <SearchClearButton
          label={clearLabel}
          onClear={() => {
            onValueChange("");
            ref.current?.focus();
          }}
        />
      )}
    </span>
  );
}
