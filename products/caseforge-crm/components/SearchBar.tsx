"use client";

import { useRef } from "react";
import { IconClose, IconSearch } from "./icons";

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
}

export function SearchBar({ value, onChange }: SearchBarProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="search-card">
      <div className="search-row">
        <div className="search-input-wrap">
          <IconSearch />
          <input
            ref={inputRef}
            type="search"
            className="search-input"
            placeholder="Name, court reference, email or phone…"
            value={value}
            onChange={(e) => onChange(e.target.value)}
            autoFocus
            aria-label="Search clients and matters"
          />
          {value !== "" && (
            <button
              type="button"
              className="cf-btn cf-btn--icon cf-btn--compact search-clear"
              aria-label="Clear the search"
              title="Clear the search"
              onClick={() => {
                onChange("");
                inputRef.current?.focus();
              }}
            >
              <IconClose aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
