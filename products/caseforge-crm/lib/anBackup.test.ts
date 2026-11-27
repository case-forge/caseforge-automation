import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { restoreIfLocalEmpty, pushBackup } from "./anBackup";
import { loadDrafts, loadWorkingCopy, saveDraft, saveWorkingCopy } from "./anDrafts";

class MemoryStorage {
  private data = new Map<string, string>();
  getItem(key: string) {
    return this.data.has(key) ? this.data.get(key)! : null;
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
}

const WORKING = { caller: "client" as const, callerOther: "", noteText: "Client rang about the hearing", kind: "call" as const };
const DRAFT = { id: "1-abc", savedAt: "2026-10-09T09:00:00Z", caller: "court" as const, callerOther: "", noteText: "Listing", kind: "call" as const };

beforeEach(() => {
  vi.stubGlobal("window", { localStorage: new MemoryStorage() });
});
afterEach(() => {
  vi.unstubAllGlobals();
});

function serverReturns(body: unknown, onCall?: () => void) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      onCall?.();
      return Response.json(body);
    }),
  );
}

describe("restoreIfLocalEmpty", () => {
  it("restores the server copy into an empty browser", async () => {
    serverReturns({ working: WORKING, drafts: [DRAFT] });
    const restored = await restoreIfLocalEmpty("435");
    expect(restored).toEqual({ working: WORKING, drafts: [DRAFT] });
    expect(loadWorkingCopy("435").noteText).toBe("Client rang about the hearing");
    expect(loadDrafts("435")).toEqual([DRAFT]);
  });

  it("leaves a browser that already has its own note alone, without asking the server", async () => {
    saveWorkingCopy("435", { ...WORKING, noteText: "Typed here" });
    serverReturns({ working: WORKING, drafts: [DRAFT] });
    expect(await restoreIfLocalEmpty("435")).toBeNull();
    expect(loadWorkingCopy("435").noteText).toBe("Typed here");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("does not overwrite what was typed while the server was answering", async () => {
    serverReturns({ working: WORKING, drafts: [DRAFT] }, () => saveWorkingCopy("435", { ...WORKING, noteText: "Typed meanwhile" }));
    expect(await restoreIfLocalEmpty("435")).toBeNull();
    expect(loadWorkingCopy("435").noteText).toBe("Typed meanwhile");
    expect(loadDrafts("435")).toEqual([]);
  });

  it("restores nothing when the server has nothing, or cannot be reached", async () => {
    serverReturns({ working: null, drafts: [] });
    expect(await restoreIfLocalEmpty("435")).toBeNull();
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    expect(await restoreIfLocalEmpty("435")).toBeNull();
  });
});

describe("pushBackup", () => {
  it("sends the current typing box and drafts for the matter", async () => {
    saveWorkingCopy("435", WORKING);
    saveDraft("435", { ...WORKING, noteText: "A draft" });
    const fetchMock = vi.fn(async () => Response.json({ working: null, drafts: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await pushBackup("435");
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/attendance-notes/backup");
    const body = JSON.parse(String(init.body));
    expect(body.matter_id).toBe("435");
    expect(body.working.noteText).toBe("Client rang about the hearing");
    expect(body.drafts).toHaveLength(1);
  });

  it("sends an empty copy when there is nothing locally, so the server copy goes too", async () => {
    const fetchMock = vi.fn(async () => Response.json({ working: null, drafts: [] }));
    vi.stubGlobal("fetch", fetchMock);
    await pushBackup("435");
    const body = JSON.parse(String((fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1].body));
    expect(body.working).toBeNull();
    expect(body.drafts).toEqual([]);
  });

  it("never throws when the server cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    await expect(pushBackup("435")).resolves.toBeUndefined();
  });
});
