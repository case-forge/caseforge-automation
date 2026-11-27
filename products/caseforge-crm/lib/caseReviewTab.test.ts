import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GET as exportRoute } from "../app/api/case-review/export/route";
import { GET as readRoute } from "../app/api/case-review/route";
import { POST as saveRoute } from "../app/api/case-review/save/route";
import { BLANK_ANSWER, countLine, countsOf, isAnswered, longDate, optionsOf, sameAnswer, savedLine } from "./caseReviewTypes";
import type { CaseReview, CaseReviewAnswer, CaseReviewRow } from "./caseReviewTypes";
import { STUB_CASE_REVIEW_FORMS, STUB_CASE_REVIEW_TODAY, stubCaseReview, stubSaveCaseReview } from "./stubCaseReview";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");
const tab = read("../components/CaseReviewTab.tsx");
const detail = read("../components/DetailPanel.tsx");

const allRows = (): CaseReviewRow[] => STUB_CASE_REVIEW_FORMS.flatMap((f) => f.sections.flatMap((s) => s.rows));
const row = (key: string): CaseReviewRow => allRows().find((r) => r.key === key)!;
const answer = (fields: Partial<CaseReviewAnswer>): CaseReviewAnswer => ({ ...BLANK_ANSWER, ...fields });
const caseReview = (matterId: string, reviewDate = ""): CaseReview => {
  const out = stubCaseReview(matterId, reviewDate);
  if ("error" in out) throw new Error(out.error);
  return out;
};
const legalKeys = (): string[] => STUB_CASE_REVIEW_FORMS[0].sections.find((s) => s.key === "legal")!.rows.map((r) => r.key);

describe("The CaseReview tab", () => {
  it("sits before the Activity log on the extra-details page and is keyed by matter", () => {
    const tabs = detail.slice(detail.indexOf("const EXTRA_TABS"), detail.indexOf("interface CaseTab"));
    expect(tabs).toMatch(/\["case-review", "Case review"\],\s*\["activity", "Activity log"\]/);
    expect(detail).toContain('detailTab === "case-review" && matterId && <CaseReviewTab key={matterId} matterId={matterId} />');
  });

  it("has the two forms, with every row of each as a control", () => {
    expect(STUB_CASE_REVIEW_FORMS.map((f) => f.title)).toEqual(["File Review Form", "File Summary Sheet"]);
    expect(STUB_CASE_REVIEW_FORMS[0].sections.map((s) => s.title)).toEqual(["File details", "Procedural Review", "Legal Review"]);
    expect(STUB_CASE_REVIEW_FORMS[1].sections.map((s) => s.title)).toEqual(["File details", "Commencement", "Progress", "Conclusion"]);
    expect(allRows()).toHaveLength(8 + 37 + 11 + 4 + 10 + 3 + 10);
    expect(tab).toContain("form.sections.map(");
    expect(tab).toContain("group.rows.map(");
    for (const r of allRows()) expect(["ynna", "yn", "choice", "text", "longtext", "date", "signoff"]).toContain(r.kind);
  });

  it("says it files nothing and runs no Case flow step", () => {
    expect(tab).toContain("Nothing is filed in the client&apos;s folder and no Case flow step is run.");
    expect(tab).not.toContain("/api/pipeline");
    expect(tab).not.toContain("/api/lexcel");
  });
});

describe("a row's answers and when it is complete", () => {
  it("offers Yes / No / N/A, the row's own choices, and N/A on a sign-off unless it is the conflict check", () => {
    expect(optionsOf(row("r_opening_completed")).map(([, l]) => l)).toEqual(["Yes", "No", "N/A"]);
    expect(optionsOf(row("r_face_to_face")).map(([, l]) => l)).toEqual(["Yes", "No"]);
    expect(optionsOf(row("s_risk_assigned")).map(([, l]) => l)).toEqual(["Normal", "High"]);
    expect(optionsOf(row("s_key_dates_backup")).map(([, l]) => l)).toEqual(["Outlook Calendar", "Outlook Tasks", "Desk Diary", "Other"]);
    expect(optionsOf(row("s_cdd")).map(([, l]) => l)).toEqual(["N/A"]);
    expect(optionsOf(row("s_conflict")).map(([, l]) => l)).toEqual(["Yes", "No"]);
  });

  it("follows each control", () => {
    expect(isAnswered(row("r_opening_completed"), undefined)).toBe(false);
    expect(isAnswered(row("r_opening_completed"), answer({ value: "na" }))).toBe(true);
    expect(isAnswered(row("r_legal_comments"), answer({ text: "   " }))).toBe(false);
    expect(isAnswered(row("r_legal_comments"), answer({ text: "None." }))).toBe(true);
    expect(isAnswered(row("s_cdd"), answer({ value: "na" }))).toBe(true);
    expect(isAnswered(row("s_cdd"), answer({ initials: "AB" }))).toBe(false);
    expect(isAnswered(row("s_cdd"), answer({ date: "2026-10-01" }))).toBe(false);
    expect(isAnswered(row("s_cdd"), answer({ initials: "AB", date: "2026-10-01" }))).toBe(true);
    expect(isAnswered(row("s_conflict"), answer({ initials: "AB", date: "2026-10-01" }))).toBe(false);
    expect(isAnswered(row("s_conflict"), answer({ value: "yes", initials: "AB", date: "2026-10-01" }))).toBe(true);
  });

  it("counts what is left, leaving optional rows out, in words", () => {
    const review = STUB_CASE_REVIEW_FORMS[0];
    expect(countsOf(review, {})).toEqual({ total: 52, answered: 0, unanswered: 52 });
    expect(countsOf(STUB_CASE_REVIEW_FORMS[1], {})).toEqual({ total: 23, answered: 0, unanswered: 23 });
    expect(countLine({ total: 52, answered: 4, unanswered: 48 })).toBe("4 of 52 answered, 48 still to answer.");
    expect(countLine({ total: 23, answered: 23, unanswered: 0 })).toBe("All 23 rows answered.");
    expect(tab).toContain("countLine(counts)");
    expect(tab).toContain("Show only rows still to answer");
    expect(tab).toContain('{done ? "Answered" : row.optional ? "Optional" : "To answer"}');
  });

  it("writes dates and the saved line the long way", () => {
    expect(longDate("2026-10-02")).toBe("2 October 2026");
    expect(longDate("2026-10-12T09:00:00Z")).toBe("12 October 2026");
    expect(longDate("soon")).toBe("soon");
    expect(savedLine({ review_date: "2026-10-12", saved: false, saved_by: "", saved_utc: "" })).toBe("Review of 12 October 2026: not saved yet.");
    expect(savedLine({ review_date: "2026-10-05", saved: true, saved_by: "Sam", saved_utc: "2026-10-06T08:00:00Z" })).toBe(
      "Review of 5 October 2026: saved by Sam on 6 October 2026.",
    );
  });
});

describe("prefill in the stub, as on the hub", () => {
  it("fills a bare matter only from its own record, each row with its source", () => {
    const a = caseReview("9001");
    expect(a.saved).toBe(false);
    expect(a.review_date).toBe(STUB_CASE_REVIEW_TODAY);
    expect(a.versions).toEqual([]);
    expect(Object.keys(a.answers).sort()).toEqual(["r_client_name", "r_date_opened", "r_file_reference", "r_matter_type", "s_client_name", "s_matter_number", "s_summary"]);
    expect(Object.values(a.answers).every((x) => x.source !== "")).toBe(true);
    expect(a.counts.review).toEqual({ total: 52, answered: 4, unanswered: 48 });
  });

  it("never fills the Legal Review or a reviewer's name, on any stub matter's fresh review", () => {
    const person = [...legalKeys(), "r_procedural_reviewer", "r_legal_reviewer"];
    expect(legalKeys()).toHaveLength(11);
    for (const id of ["9001", "9002", "9003", "stub-case-review-other"]) {
      const fresh = caseReview(id, "2026-10-11");
      expect(fresh.saved).toBe(false);
      for (const key of person) expect(fresh.answers[key]).toBeUndefined();
      expect(Object.keys(fresh.notes).some((k) => k.toLowerCase().includes("legal"))).toBe(false);
    }
    expect(tab).toContain("The system never fills or suggests an answer here.");
  });

  it("takes the client care letter's date from the Lexcel record and leaves the sign-off to a person", () => {
    const a = caseReview("9002", "2026-10-11");
    const ccl = a.answers.s_ccl_sent;
    expect(ccl).toMatchObject({ date: "2026-09-22", initials: "", value: "" });
    expect(ccl.source).toContain("The date it was sent is not recorded");
    expect(isAnswered(row("s_ccl_sent"), ccl)).toBe(false);
    expect(caseReview("9001").answers.s_ccl_sent).toBeUndefined();
    expect(caseReview("9001").notes["End of Case Client Care Letter"]).toContain("no closing letter is recorded as made");
    expect(a.answers.s_source.text).toBe("referrer referral");
    expect(a.answers.s_key_dates.text).toBe("6 October 2026: First hearing, Anytown Family Court");
  });

  it("shows where an answer came from, and only while it is still the system's", () => {
    expect(tab).toContain("Not typed here. {a.source}");
    expect(tab).toContain("next.source = original && sameAnswer(original, next) ? original.source : \"\";");
    expect(sameAnswer(answer({ text: "a", source: "x" }), answer({ text: "a" }))).toBe(true);
    expect(sameAnswer(answer({ text: "a" }), answer({ text: "b" }))).toBe(false);
  });
});

describe("saving, and reviewing a file again", () => {
  it("starts 9002 partly filled and 9003 complete with an earlier review kept", () => {
    const part = caseReview("9002");
    expect(part.saved).toBe(true);
    expect(part.review_date).toBe("2026-10-05");
    expect(part.counts.review.unanswered).toBeGreaterThan(0);
    expect(part.counts.review.answered).toBeGreaterThan(4);
    const full = caseReview("9003");
    expect(full.review_date).toBe("2026-10-08");
    expect(full.counts.review.unanswered).toBe(0);
    expect(full.counts.summary.unanswered).toBe(0);
    expect(full.versions.map((v) => v.review_date)).toEqual(["2026-10-08", "2026-07-01"]);
    expect(caseReview("9003", "2026-07-01").answers.r_opening_completed.value).toBe("no");
  });

  it("saves under the review date with who saved it, and drops the source of a changed answer", () => {
    const id = "stub-case-review-save";
    const draft = caseReview(id);
    const out = stubSaveCaseReview(id, draft.review_date, { ...draft.answers, r_matter_type: answer({ text: "Injunction" }), r_legal_issues: answer({ value: "yes", source: "The system" }) }, "Sam");
    if ("error" in out) throw new Error(out.error);
    expect(out.saved).toBe(true);
    expect(out.saved_by).toBe("Sam");
    expect(out.answers.r_client_name.source).not.toBe("");
    expect(out.answers.r_matter_type).toEqual(answer({ text: "Injunction" }));
    expect(out.answers.r_legal_issues.source).toBe("");
    expect(caseReview(id).answers.r_matter_type.text).toBe("Injunction");
    expect(out.versions).toHaveLength(1);
  });

  it("keeps the earlier review when a second is saved, carrying the summary sheet over and starting the file review again", () => {
    const id = "stub-case-review-again";
    stubSaveCaseReview(id, "2026-10-02", { r_opening_completed: answer({ value: "no" }), s_cdd: answer({ initials: "AB", date: "2026-10-01" }) }, "Sam");
    const fresh = caseReview(id, "2026-10-12");
    expect(fresh.saved).toBe(false);
    expect(fresh.answers.r_opening_completed).toBeUndefined();
    expect(fresh.answers.s_cdd).toMatchObject({ initials: "AB", source: "Carried over from the review of 2 October 2026." });
    stubSaveCaseReview(id, "2026-10-12", { ...fresh.answers, r_opening_completed: answer({ value: "yes" }) }, "Jordan");
    expect(caseReview(id).versions.map((v) => [v.review_date, v.saved_by])).toEqual([["2026-10-12", "Jordan"], ["2026-10-02", "Sam"]]);
    expect(caseReview(id, "2026-10-02").answers.r_opening_completed.value).toBe("no");
    expect(tab).toContain("Start a new review");
    expect(tab).toContain("An earlier review is kept as it was saved.");
  });

  it("refuses a save it cannot record", () => {
    const id = "stub-case-review-refuse";
    expect(stubSaveCaseReview(id, "2026-10-12", {}, " ")).toEqual({ error: "type your name first" });
    expect(stubSaveCaseReview(id, "2026-10-13", {}, "Sam")).toEqual({ error: "the review date cannot be in the future" });
    expect(stubSaveCaseReview(id, "12/10/2026", {}, "Sam")).toEqual({ error: "the review date must be a date" });
    expect(stubSaveCaseReview(id, "2026-10-12", { r_opening_completed: answer({ value: "maybe" }) }, "Sam")).toEqual({ error: "Completed?: that is not one of its answers" });
    expect(stubSaveCaseReview(id, "2026-10-12", { s_conflict: answer({ value: "na" }) }, "Sam")).toHaveProperty("error");
    expect(caseReview(id).versions).toEqual([]);
    expect(tab).toContain("This review has changes that are not saved. Leave it without saving?");
  });
});

describe("the viewer's case review routes", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });
  const nextGet = async (path: string) => {
    const { NextRequest } = await import("next/server");
    return new NextRequest(`http://localhost${path}`);
  };

  it("serve the stub, and refuse a request with nothing to act on", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const res = await readRoute(await nextGet("/api/case-review?matter_id=9001"));
    expect(res.status).toBe(200);
    expect((await res.json()).forms).toHaveLength(2);
    expect((await readRoute(await nextGet("/api/case-review"))).status).toBe(400);
    expect((await readRoute(await nextGet("/api/case-review?matter_id=9001&review_date=2027-01-01"))).status).toBe(422);
    const { NextRequest } = await import("next/server");
    const post = (body: unknown) => saveRoute(new NextRequest("http://localhost/api/case-review/save", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }));
    const saved = await post({ matter_id: "stub-case-review-route", review_date: "2026-10-12", answers: { r_opening_completed: { value: "yes" } } });
    expect(saved.status).toBe(200);
    expect((await saved.json()).saved_by).toBe("tailnet");
  });

  it("has no Word form in stub mode and says so, and asks the hub for one otherwise", async () => {
    vi.stubEnv("CASEFORGE_HUB_API_STUB", "1");
    const stub = await exportRoute(await nextGet("/api/case-review/export?matter_id=9001&form=review"));
    expect(stub.status).toBe(501);
    expect((await stub.json()).error).toContain("stub mode has no download");
    expect((await exportRoute(await nextGet("/api/case-review/export?matter_id=9001&form=bundle"))).status).toBe(400);

    vi.stubEnv("CASEFORGE_HUB_API_STUB", "");
    vi.stubEnv("CASEFORGE_HUB_API_URL", "http://hub.invalid:8770");
    vi.stubEnv("CASEFORGE_CHAT_API_TOKEN", "synthetic-test-token");
    const seen: string[] = [];
    vi.stubGlobal("fetch", async (url: URL) => {
      seen.push(String(url));
      return new Response("PK-synthetic", {
        headers: { "content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "content-disposition": 'attachment; filename="File-Review-PERSON-2026-10-12.docx"' },
      });
    });
    const real = await exportRoute(await nextGet("/api/case-review/export?matter_id=603&form=review&review_date=2026-10-12"));
    expect(real.status).toBe(200);
    expect(seen).toEqual(["http://hub.invalid:8770/client-viewer/case-review/export.docx?matter_id=603&form=review&review_date=2026-10-12"]);
    expect(real.headers.get("content-disposition")).toBe('attachment; filename="File-Review-PERSON-2026-10-12.docx"');
    expect(await real.text()).toBe("PK-synthetic");
    expect(tab).toContain("Download the ${f.title} as Word");
    expect(tab).toContain("Save first: the Word form is made from the saved review.");
  });
});
