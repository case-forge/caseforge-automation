import { describe, expect, it } from "vitest";
import type { StatusBoardItem } from "./matterMilestones";
import { BOARD_COLUMNS, nextSort, sortItems } from "./statusBoardColumns";

const item = (matter_id: string, client_name: string, over: Partial<StatusBoardItem> = {}, milestones: Partial<StatusBoardItem["milestones"]> = {}): StatusBoardItem => ({
  matter_id,
  client_name,
  date_joined: "",
  loa: "",
  initial_ws: "",
  order_codes: [],
  book: "",
  milestones: { contacted: "", papers_signed: "", filed: "", service_requested: "", served: "", legal_aid_done: "", invoice_paid: "", laa_interim_cert: "", laa_final_cert: "", ...milestones },
  ...over,
});

describe("the board's columns", () => {
  it("start in the order the firm asked for", () => {
    expect(BOARD_COLUMNS.map((c) => c.label)).toEqual([
      "Referred", "Contacted", "LoA Signed", "WS Signed", "Filed to Court", "Service Requested", "Served", "LAA Signed", "LAA Interim Cert", "LAA Final Cert",
    ]);
  });

  it("read each stage from the right place on a row", () => {
    const row = item("1", "A", { date_joined: "2026-10-01", loa: "L", initial_ws: "W" }, { contacted: "C", filed: "F", service_requested: "R", served: "V", legal_aid_done: "S", laa_interim_cert: "I", laa_final_cert: "Z" });
    expect(BOARD_COLUMNS.map((c) => c.value(row))).toEqual(["2026-10-01", "C", "L", "W", "F", "R", "V", "S", "I", "Z"]);
  });
});

describe("sorting", () => {
  it("cycles ascending, descending, off on one heading and restarts on another", () => {
    const first = nextSort(null, "filed");
    expect(first).toEqual({ by: "filed", dir: "asc" });
    expect(nextSort(first, "filed")).toEqual({ by: "filed", dir: "desc" });
    expect(nextSort({ by: "filed", dir: "desc" }, "filed")).toBeNull();
    expect(nextSort(first, "loa")).toEqual({ by: "loa", dir: "asc" });
  });

  it("orders a stage by its stored time, even within one day, and always puts the blanks last", () => {
    const rows = [
      item("1", "Late", {}, { filed: "2026-10-05T16:00:00Z" }),
      item("2", "None"),
      item("3", "Early", {}, { filed: "2026-10-05T08:00:00Z" }),
    ];
    expect(sortItems(rows, { by: "filed", dir: "asc" }).map((r) => r.client_name)).toEqual(["Early", "Late", "None"]);
    expect(sortItems(rows, { by: "filed", dir: "desc" }).map((r) => r.client_name)).toEqual(["Late", "Early", "None"]);
  });

  it("sorts the date joined column and the client and number columns", () => {
    const rows = [item("10", "Bee", { date_joined: "2026-09-02" }), item("9", "Ann", { date_joined: "2026-09-01" })];
    expect(sortItems(rows, { by: "joined", dir: "asc" }).map((r) => r.client_name)).toEqual(["Ann", "Bee"]);
    expect(sortItems(rows, { by: "client", dir: "desc" }).map((r) => r.client_name)).toEqual(["Bee", "Ann"]);
    expect(sortItems(rows, { by: "no", dir: "asc" }).map((r) => r.matter_id)).toEqual(["9", "10"]);
  });

  it("leaves the order alone when no sort is chosen, and never changes the input", () => {
    const rows = [item("2", "B"), item("1", "A")];
    expect(sortItems(rows, null).map((r) => r.matter_id)).toEqual(["2", "1"]);
    sortItems(rows, { by: "no", dir: "asc" });
    expect(rows.map((r) => r.matter_id)).toEqual(["2", "1"]);
  });
});
