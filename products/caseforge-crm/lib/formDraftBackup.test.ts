import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fetchServerDraft, removeServerDraft, scheduleServerDraft } from "./formDraftBackup";

beforeEach(() => {
  vi.useFakeTimers();
  vi.stubGlobal("window", {});
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe("fetchServerDraft", () => {
  it("returns the saved draft for the matter and form", async () => {
    const fetchMock = vi.fn(async () => Response.json({ saved_at: 1000, data: { note: "x" } }));
    vi.stubGlobal("fetch", fetchMock);
    expect(await fetchServerDraft("435", "client-edit")).toEqual({ savedAt: 1000, data: { note: "x" } });
    expect(String((fetchMock.mock.calls[0] as unknown[])[0])).toBe("/api/form-drafts/backup?matter_id=435&form_id=client-edit");
  });

  it("is null when there is no copy, the server fails or the network throws", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Response.json({ saved_at: null, data: null })));
    expect(await fetchServerDraft("435", "client-edit")).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => new Response("no", { status: 502 })));
    expect(await fetchServerDraft("435", "client-edit")).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new Error("offline"))));
    expect(await fetchServerDraft("435", "client-edit")).toBeNull();
    expect(await fetchServerDraft("", "client-edit")).toBeNull();
  });
});

describe("scheduleServerDraft and removeServerDraft", () => {
  it("sends only the last change, a moment after it", async () => {
    const fetchMock = vi.fn(async () => Response.json({}));
    vi.stubGlobal("fetch", fetchMock);
    scheduleServerDraft("435", "client-edit", { note: "a" }, 5);
    scheduleServerDraft("435", "client-edit", { note: "ab" }, 6);
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1600);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ matter_id: "435", form_id: "client-edit", saved_at: 6, data: { note: "ab" } });
  });

  it("removing cancels a waiting push and sends a null draft", async () => {
    const fetchMock = vi.fn(async () => Response.json({}));
    vi.stubGlobal("fetch", fetchMock);
    scheduleServerDraft("435", "client-edit", { note: "a" });
    removeServerDraft("435", "client-edit");
    await vi.advanceTimersByTimeAsync(3000);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const init = (fetchMock.mock.calls[0] as unknown[])[1] as RequestInit;
    expect(JSON.parse(String(init.body))).toEqual({ matter_id: "435", form_id: "client-edit", saved_at: null, data: null });
  });
});
