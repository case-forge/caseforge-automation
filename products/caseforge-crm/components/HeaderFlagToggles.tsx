"use client";

import { useEffect, useRef, useState } from "react";
import { IconFlag, IconStar } from "@/components/icons";
import { runFlagToggle } from "@/lib/flagToggle";

const TOGGLES = [
  { name: "flagged", label: "Flag", Icon: IconFlag },
  { name: "starred", label: "Star", Icon: IconStar },
] as const;

export interface FlagKinds {
  shared: Record<string, boolean>;
  personal: Record<string, boolean>;
  personalReasons: Record<string, string>;
}

export const NO_KINDS: FlagKinds = { shared: {}, personal: {}, personalReasons: {} };

export function flagButtonLabel(kinds: FlagKinds, autoReason: string): string {
  const own = kinds.personal.flagged ? `Your flag${kinds.personalReasons.flagged ? `: ${kinds.personalReasons.flagged}` : ""}` : "";
  const auto = kinds.shared.flagged ? `Automatic flag${autoReason ? `: ${autoReason}` : ""}` : "";
  if (auto && own) return `${auto}. ${own}`;
  if (auto) return `${auto}. Press to clear it for everyone`;
  if (own) return own;
  return "Flag this client";
}

type Posted = { flags?: Record<string, boolean>; reasons?: Record<string, string>; shared?: Record<string, boolean>; personal?: Record<string, boolean>; personal_reasons?: Record<string, string> };

export function HeaderFlagToggles({
  matterId,
  flags,
  reasons,
  kinds = NO_KINDS,
  onKinds,
  onChanged,
}: {
  matterId: string;
  flags: Record<string, boolean>;
  reasons: Record<string, string>;

  kinds?: FlagKinds;

  onKinds?: (kinds: FlagKinds) => void;

  onChanged: (flags: Record<string, boolean>, reasons: Record<string, string>, settled: boolean) => void;
}) {
  const [error, setError] = useState<string | null>(null);
  const [asking, setAsking] = useState<"reason" | "clear" | null>(null);
  const [reason, setReason] = useState("");
  const inFlight = useRef<Set<string>>(new Set());
  const openMatter = useRef(matterId);
  openMatter.current = matterId;
  const current = useRef({ flags, reasons });
  current.current = { flags, reasons };

  useEffect(() => () => {
    openMatter.current = "";
  }, []);

  async function toggle(flagName: string, next: boolean, extra: Record<string, unknown> = {}) {
    if (inFlight.current.has(flagName)) return;
    inFlight.current.add(flagName);
    setError(null);
    const forMatter = matterId;
    const message = await runFlagToggle({
      flags,
      reasons,
      flagName,
      next,
      apply: onChanged,
      getCurrent: () => current.current,
      isStillOpen: () => openMatter.current === forMatter,
      post: async () => {
        const res = await fetch("/api/clients/matter-flags", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ matter_id: forMatter, flag_name: flagName, is_set: next, ...extra }),
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}) as { error?: string });
          throw new Error(body.error || "Could not update that flag");
        }
        const body = (await res.json()) as Posted;
        if (openMatter.current === forMatter) {
          onKinds?.({ shared: body.shared ?? {}, personal: body.personal ?? {}, personalReasons: body.personal_reasons ?? {} });
        }
        return body;
      },
    });
    inFlight.current.delete(flagName);
    if (message && openMatter.current === forMatter) setError(message);
  }

  function pressFlag() {
    if (kinds.personal.flagged) {

      void toggle("flagged", false);
    } else if (kinds.shared.flagged) {
      setAsking("clear");
    } else {
      setReason("");
      setAsking("reason");
    }
  }

  function saveReason() {
    const text = reason.trim();
    setAsking(null);
    void toggle("flagged", true, text ? { reason: text } : {});
  }

  function clearAutomatic() {
    setAsking(null);
    void toggle("flagged", false, { scope: "shared" });
  }

  return (
    <>
      {TOGGLES.map(({ name, label, Icon }) => {
        const isFlag = name === "flagged";
        const auto = isFlag && Boolean(kinds.shared.flagged);
        const own = isFlag ? Boolean(kinds.personal.flagged) : false;

        const on = isFlag ? auto || own || (flags[name] ?? false) : flags[name] ?? false;
        const text = isFlag ? flagButtonLabel(kinds, reasons.flagged ?? "") : on ? `${label}: on. Press to remove` : `${label} this client`;
        return (
          <span key={name} className="header-flag-wrap">
            <button
              type="button"
              className="cf-btn cf-btn--icon header-flag-toggle"
              data-flag={name}
              aria-pressed={on}
              aria-expanded={isFlag ? asking !== null : undefined}
              disabled={!matterId}
              title={on || !isFlag ? text : "Flag this client"}
              aria-label={on || !isFlag ? text : "Flag this client"}
              onClick={() => (isFlag ? pressFlag() : void toggle(name, !on))}
            >
              <Icon className="header-flag-toggle-icon" filled={on} aria-hidden="true" />
            </button>
            {isFlag && asking === "reason" && (
              <form
                className="header-flag-ask"
                onSubmit={(event) => {
                  event.preventDefault();
                  saveReason();
                }}
              >
                <label className="header-flag-ask-label" htmlFor="header-flag-reason">
                  Why are you flagging this client?
                </label>
                <input
                  id="header-flag-reason"
                  className="header-flag-ask-input"
                  value={reason}
                  maxLength={200}
                  autoFocus
                  onChange={(event) => setReason(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === "Escape") setAsking(null);
                  }}
                />
                <span className="header-flag-ask-actions">
                  <button type="submit" className="cf-btn cf-btn--primary">
                    Save
                  </button>
                  <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setAsking(null)}>
                    Cancel
                  </button>
                </span>
              </form>
            )}
            {isFlag && asking === "clear" && (
              <div
                className="header-flag-ask"
                role="alertdialog"
                aria-label="Clear the automatic flag"
                onKeyDown={(event) => {
                  if (event.key === "Escape") setAsking(null);
                }}
              >
                <span className="header-flag-ask-label">This clears the automatic flag for everyone</span>
                <span className="header-flag-ask-actions">
                  <button type="button" className="cf-btn cf-btn--primary" autoFocus onClick={clearAutomatic}>
                    Clear it
                  </button>
                  <button type="button" className="cf-btn cf-btn--neutral" onClick={() => setAsking(null)}>
                    Cancel
                  </button>
                </span>
              </div>
            )}
          </span>
        );
      })}
      {error && (
        <span className="client-edits-error header-flag-toggle-error" role="alert">
          {error}
        </span>
      )}
    </>
  );
}
