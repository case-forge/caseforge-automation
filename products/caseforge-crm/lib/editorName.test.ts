import { afterEach, describe, expect, it, vi } from "vitest";
import { currentEditorName, loadEditorName, resetEditorNameForTests } from "./editorName";

afterEach(() => resetEditorNameForTests());

describe("the signed-in name in the browser", () => {
  it("is read once from /api/me and then kept", async () => {
    const fetcher = vi.fn(async (_url: string, _init?: RequestInit) => new Response(JSON.stringify({ name: " Sam ", signed_in: true })));
    expect(currentEditorName()).toBe("");
    expect(await loadEditorName(fetcher as unknown as typeof fetch)).toBe("Sam");
    expect(await loadEditorName(fetcher as unknown as typeof fetch)).toBe("Sam");
    expect(fetcher).toHaveBeenCalledTimes(1);
    expect(fetcher.mock.calls[0]?.[0]).toBe("/api/me");
    expect(currentEditorName()).toBe("Sam");
  });

  it("is empty when the read fails, and is tried again on the next call", async () => {
    const failing = vi.fn(async () => {
      throw new Error("offline");
    });
    expect(await loadEditorName(failing as unknown as typeof fetch)).toBe("");
    const refused = vi.fn(async () => new Response("{}", { status: 403 }));
    expect(await loadEditorName(refused as unknown as typeof fetch)).toBe("");
    const ok = vi.fn(async () => new Response(JSON.stringify({ name: "tailnet", signed_in: false })));
    expect(await loadEditorName(ok as unknown as typeof fetch)).toBe("tailnet");
  });
});
