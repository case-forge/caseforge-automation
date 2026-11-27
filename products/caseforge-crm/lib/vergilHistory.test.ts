import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  conversationAsText,
  loadVergilHistory,
  saveVergilConversation,
  setVergilConversationTitle,
  vergilRecencyBucket,
} from "./vergilHistory";
import type { VergilConversation, VergilMessage } from "./vergilHistory";

describe("conversationAsText", () => {
  it("pairs You/Vergil lines, dropping the context primer and errors", () => {
    const messages: VergilMessage[] = [
      { role: "context", text: "Client: Stub Testperson..." },
      { role: "user", text: "What is the next hearing?" },
      { role: "vergil", text: "**3 November** at 10:30, Central Family Court." },
      { role: "error", text: "Vergil is unavailable right now." },
    ];
    expect(conversationAsText(messages)).toBe(
      "You: What is the next hearing?\n\nVergil: **3 November** at 10:30, Central Family Court.",
    );
  });

  it("is empty for an empty or context-only transcript", () => {
    expect(conversationAsText([])).toBe("");
    expect(conversationAsText([{ role: "context", text: "..." }])).toBe("");
  });

  it("keeps markdown source as-is, for pasting rather than for re-rendering", () => {
    const text = conversationAsText([{ role: "vergil", text: "- one\n- two" }]);
    expect(text).toBe("Vergil: - one\n- two");
  });
});

describe("vergilRecencyBucket", () => {
  const now = new Date(2026, 8, 24, 12, 0);

  it("uses calendar days, not rolling 24-hour windows", () => {
    expect(vergilRecencyBucket(new Date(2026, 8, 24, 0, 5).toISOString(), now)).toBe("Today");
    expect(vergilRecencyBucket(new Date(2026, 8, 23, 23, 50).toISOString(), now)).toBe("Yesterday");
  });

  it("buckets the last week and everything older", () => {
    expect(vergilRecencyBucket(new Date(2026, 8, 20, 9, 0).toISOString(), now)).toBe("Previous 7 days");
    expect(vergilRecencyBucket(new Date(2026, 8, 17, 9, 0).toISOString(), now)).toBe("Previous 7 days");
    expect(vergilRecencyBucket(new Date(2026, 8, 16, 9, 0).toISOString(), now)).toBe("Older");
  });

  it("reads an unparseable date as Today rather than burying it", () => {
    expect(vergilRecencyBucket("not a date", now)).toBe("Today");
  });
});

describe("30-day expiry", () => {
  function fakeStorage() {
    const store = new Map<string, string>();
    return {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    };
  }
  function conversation(sessionId: string, updatedAt: Date): VergilConversation {
    return {
      sessionId,
      matterId: "9001",
      startedAt: updatedAt.toISOString(),
      updatedAt: updatedAt.toISOString(),
      firstQuestion: "q",
      messages: [],
    };
  }

  beforeEach(() => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
  });

  it("drops conversations last updated more than 30 days ago, keeps newer ones", () => {
    const day = 86_400_000;
    saveVergilConversation(conversation("old", new Date(Date.now() - 31 * day)));
    saveVergilConversation(conversation("fresh", new Date(Date.now() - 29 * day)));
    expect(loadVergilHistory("9001").map((c) => c.sessionId)).toEqual(["fresh"]);
  });

  it("writes the pruned list back so a stale entry does not linger in storage", () => {
    const day = 86_400_000;
    saveVergilConversation(conversation("old", new Date(Date.now() - 40 * day)));
    loadVergilHistory("9001");
    const raw = (window.localStorage as unknown as { getItem: (k: string) => string | null }).getItem(
      "caseforge-client-viewer:vergil-history:9001",
    );
    expect(JSON.parse(raw ?? "[]")).toEqual([]);
  });

  it("keeps an entry whose date cannot be read rather than guessing it is stale", () => {
    const bad = conversation("odd", new Date());
    bad.updatedAt = "garbage";
    saveVergilConversation(bad);
    expect(loadVergilHistory("9001").map((c) => c.sessionId)).toEqual(["odd"]);
  });
});

describe("setVergilConversationTitle", () => {
  function fakeStorage() {
    const store = new Map<string, string>();
    return {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    };
  }
  function saved(sessionId: string): VergilConversation {
    const now = new Date().toISOString();
    return { sessionId, matterId: "9001", startedAt: now, updatedAt: now, firstQuestion: "q", messages: [] };
  }

  beforeEach(() => {
    vi.stubGlobal("window", { localStorage: fakeStorage() });
  });

  it("titles the matching conversation and leaves the others alone", () => {
    saveVergilConversation(saved("a"));
    saveVergilConversation(saved("b"));
    setVergilConversationTitle("9001", "a", "Next hearing and order");
    const byId = Object.fromEntries(loadVergilHistory("9001").map((c) => [c.sessionId, c.title]));
    expect(byId).toEqual({ a: "Next hearing and order", b: undefined });
  });

  it("does nothing for a conversation that was never saved", () => {
    setVergilConversationTitle("9001", "missing", "Whatever");
    expect(loadVergilHistory("9001")).toEqual([]);
  });
});

describe("sourcesSummary", () => {
  it("says how many sources were checked, from the server's own list", async () => {
    const { sourcesSummary } = await import("./vergilHistory");
    expect(sourcesSummary({ sources_checked: ["a", "b", "c", "d"], gaps: [] })).toBe("Checked 4 sources");
    expect(sourcesSummary({ sources_checked: ["a"], gaps: ["x"] })).toBe("Checked 1 source");
  });

  it("shows nothing when nothing was checked or there is no record", async () => {
    const { sourcesSummary } = await import("./vergilHistory");
    expect(sourcesSummary({ sources_checked: [], gaps: [] })).toBe("");
    expect(sourcesSummary(undefined)).toBe("");
  });
});
