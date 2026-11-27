import { afterEach, describe, expect, it, vi } from "vitest";
import { clientGuessLabel, dateSourceLabel, fetchScans, pagesLabel, readAtLabel, sameContentsNote, scanDateLabel, scansSummary, sortScans } from "./scans";
import type { ScanRow, ScansTable } from "./scansTypes";
import { stubScans } from "./stubScans";

function row(name: string, part: Partial<ScanRow> = {}): ScanRow {
  return { id: name, name, scan_date: "", date_source: "unknown", uploaded_utc: "", modified_utc: "", pages: null, possible_client: "", folder: "F", web_url: "", size_bytes: 1, same_contents_as: [], ...part };
}

function table(part: Partial<ScansTable> = {}): ScansTable {
  return { folder: "F", readable: true, total: 0, folders_not_listed: 0, read_utc: "", rows: [], ...part };
}

afterEach(() => vi.unstubAllGlobals());

describe("the words in each cell", () => {
  it("writes the date out and never lets a time zone move the day", () => {
    expect(scanDateLabel("2026-09-04")).toBe("4 Sep 2026");
    expect(scanDateLabel("2026-01-31")).toBe("31 Jan 2026");
    expect(scanDateLabel("")).toBe("No date");
    expect(scanDateLabel("2026-13-01")).toBe("No date");
  });

  it("says where the date came from, and marks every date that is not from the file name", () => {
    expect(dateSourceLabel("filename")).toBe("From the file name");
    expect(dateSourceLabel("uploaded")).toContain("Upload date");
    expect(dateSourceLabel("modified")).toContain("Last changed date");
    for (const source of ["uploaded", "modified"] as const) expect(dateSourceLabel(source)).toContain("no date in the file name");
    expect(dateSourceLabel("unknown")).toContain("No date");
  });

  it("words the client as a guess and never as a fact", () => {
    expect(clientGuessLabel("TESTPERSON")).toBe("Possibly TESTPERSON");
    expect(clientGuessLabel("  ")).toBe("No guess");
  });

  it("shows pages only when known", () => {
    expect(pagesLabel(3)).toBe("3");
    expect(pagesLabel(null)).toBe("Not known");
    expect(pagesLabel(0)).toBe("Not known");
  });

  it("names the other rows with the same contents and says both are listed", () => {
    expect(sameContentsNote([])).toBe("");
    expect(sameContentsNote(["A.pdf", "B.pdf"])).toBe("Possible duplicate: same contents as A.pdf, B.pdf. Both are listed.");
  });
});

describe("sortScans", () => {
  it("puts the newest scan date first, by the date shown, and a row with no date last", () => {
    const rows = [
      row("named-old", { scan_date: "2026-09-04", date_source: "filename", uploaded_utc: "2026-10-09T09:00:00Z" }),
      row("undated"),
      row("uploaded", { scan_date: "2026-10-01", date_source: "uploaded", uploaded_utc: "2026-10-01T09:00:00Z" }),
    ];
    expect(sortScans(rows).map((r) => r.name)).toEqual(["uploaded", "named-old", "undated"]);
  });

  it("keeps every row, two with the same name included, and does not change the list it was given", () => {
    const rows = [row("Scan.pdf", { id: "a", scan_date: "2026-09-04" }), row("Scan.pdf", { id: "b", scan_date: "2026-09-04" })];
    const sorted = sortScans(rows);
    expect(sorted.map((r) => r.id)).toEqual(["a", "b"]);
    expect(rows.map((r) => r.id)).toEqual(["a", "b"]);
  });
});

describe("scansSummary and readAtLabel", () => {
  it("counts in words, mentions sub-folders, and never calls an unread folder empty", () => {
    expect(scansSummary(table({ total: 1 }))).toBe("1 scan waiting");
    expect(scansSummary(table({ total: 0 }))).toBe("0 scans waiting");
    expect(scansSummary(table({ total: 4, folders_not_listed: 2 }))).toBe("4 scans waiting, 2 sub-folders not opened");
    expect(scansSummary(table({ readable: false }))).toBe("Folder not read");
  });

  it("gives the read time in London", () => {
    expect(readAtLabel("2026-07-01T13:05:00Z")).toBe("14:05");
    expect(readAtLabel("2026-01-05T13:05:00Z")).toBe("13:05");
    expect(readAtLabel("")).toBe("");
    expect(readAtLabel("nonsense")).toBe("");
  });
});

describe("the stub", () => {
  it("covers a filename date, both fallbacks, a guess, no guess and a flagged pair, with no row dropped", () => {
    const stub = stubScans();
    expect(stub.rows).toHaveLength(stub.total);
    expect(new Set(stub.rows.map((r) => r.date_source))).toEqual(new Set(["filename", "uploaded", "modified"]));
    expect(stub.rows.some((r) => r.possible_client)).toBe(true);
    expect(stub.rows.some((r) => !r.possible_client)).toBe(true);
    expect(stub.rows.filter((r) => r.same_contents_as.length > 0)).toHaveLength(2);
    expect(sortScans(stub.rows).map((r) => r.id)).toEqual(stub.rows.map((r) => r.id));
  });

  it("carries no amount and no rate", () => {
    expect(JSON.stringify(stubScans())).not.toMatch(/£|fee|rate|amount|cost|price|minutes/i);
  });
});

describe("fetchScans", () => {
  const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });

  it("returns the table sorted newest first", async () => {
    const fetchMock = vi.fn().mockResolvedValue(json(table({ total: 2, rows: [row("old", { scan_date: "2026-01-01" }), row("new", { scan_date: "2026-02-01" })] })));
    vi.stubGlobal("fetch", fetchMock);
    expect((await fetchScans()).rows.map((r) => r.name)).toEqual(["new", "old"]);
    expect(fetchMock).toHaveBeenCalledWith("/api/scans", { cache: "no-store" });
  });

  it("passes an unreadable folder through as a table, not an error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json(table({ readable: false }))));
    expect((await fetchScans()).readable).toBe(false);
  });

  it("fails in plain words on a hub error, a malformed answer, a lost connection and a lapsed session", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ error: "upstream request failed" }, 502)));
    await expect(fetchScans()).rejects.toThrow("Could not load the scans");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(json({ rows: "no" })));
    await expect(fetchScans()).rejects.toThrow("Could not load the scans");
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));
    await expect(fetchScans()).rejects.toThrow("Check the connection");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<html>", { headers: { "content-type": "text/html" } })));
    await expect(fetchScans()).rejects.toThrow("session has expired");
  });
});
