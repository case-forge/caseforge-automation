import { afterEach, describe, expect, it, vi } from "vitest";
import { LIST_WORDS, replyButtonLabel, setStatementReply, STATEMENT_REPLIES_CHANGED_EVENT } from "./statementReplies";
import { stubSetReply, stubStatementReplies } from "./stubStatementReplies";

describe("the smiley lists in words", () => {
  it("names each list and says how many clients are on it", () => {
    expect(replyButtonLabel("approved", 0)).toBe("Statement approved, none");
    expect(replyButtonLabel("approved", 1)).toBe("Statement approved, 1 client");
    expect(replyButtonLabel("amend", 3)).toBe("Wants changes, 3 clients");
    expect(LIST_WORDS.amend.title).toBe("Wants changes");
  });
});

describe("the stub", () => {
  it("moves a client between the lists and clears them", () => {
    expect(stubSetReply("9001", "approved", "", "Sam")).toEqual({ matter_id: "9001", state: "approved" });
    let lists = stubStatementReplies();
    expect(lists.items.find((i) => i.matter_id === "9001")?.state).toBe("approved");
    expect(stubSetReply("9001", "amend", "  Fix   the\ndates ", "Sam")).toEqual({ matter_id: "9001", state: "amend" });
    lists = stubStatementReplies();
    const row = lists.items.find((i) => i.matter_id === "9001");
    expect(row?.state).toBe("amend");
    expect(row?.note).toBe("Fix the dates");
    expect(lists.approved_count + lists.amend_count).toBe(lists.items.length);
    stubSetReply("9001", "", "", "Sam");
    expect(stubStatementReplies().items.some((i) => i.matter_id === "9001")).toBe(false);
  });

  it("refuses a missing name, a bad state and an amend with no note", () => {
    expect(stubSetReply("9001", "approved", "", " ")).toEqual({ error: "type your name first" });
    expect(stubSetReply("9001", "maybe", "", "C")).toEqual({ error: "state must be approved, amend or empty" });
    expect(stubSetReply("9001", "amend", "  ", "C")).toEqual({ error: "say what the client wants changed" });
    expect(stubSetReply("abc", "approved", "", "C")).toEqual({ error: "matter_id must be a matter number" });
  });
});

describe("recording a reply", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts it, and tells every open list to refresh", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) });
    vi.stubGlobal("fetch", fetchMock);
    const heard = vi.fn();
    vi.stubGlobal("window", { dispatchEvent: heard });
    await setStatementReply("603", "amend", "Change paragraph 4");
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ matter_id: "603", state: "amend", note: "Change paragraph 4" });
    expect(heard).toHaveBeenCalledTimes(1);
    expect((heard.mock.calls[0][0] as Event).type).toBe(STATEMENT_REPLIES_CHANGED_EVENT);
  });

  it("shows the hub's own refusal", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: async () => ({ error: "say what the client wants changed" }) }));
    vi.stubGlobal("window", { dispatchEvent: vi.fn() });
    await expect(setStatementReply("603", "amend", "")).rejects.toThrow("say what the client wants changed");
  });
});
