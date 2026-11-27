import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_SCANNED_FOLDER, loadScannedFolder, saveScannedFolder, validScannedFolder } from "./scannedFolder";

afterEach(() => vi.unstubAllGlobals());

describe("scanned folder setting", () => {
  it("accepts an empty value (the default) and a tidy relative path, and refuses the rest", () => {
    for (const ok of ["", "  ", "Company_Data/Scanned Docs", "/company_data/post-room/"]) expect(validScannedFolder(ok)).toBe(true);
    for (const bad of ["a/../b", "a//b", "a\\b", "./a", "x".repeat(201), 3, null]) expect(validScannedFolder(bad)).toBe(false);
  });

  it("falls back to the default when the hub cannot be read", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("down")));
    expect((await loadScannedFolder()).path).toBe(DEFAULT_SCANNED_FOLDER);
  });

  it("does not send an invalid path, and returns the path now in force on a save", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ path: "company_data/post-room", default: DEFAULT_SCANNED_FOLDER })));
    vi.stubGlobal("fetch", fetchMock);
    expect(await saveScannedFolder("a/../b")).toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
    expect((await saveScannedFolder("company_data/post-room"))?.path).toBe("company_data/post-room");
  });
});
