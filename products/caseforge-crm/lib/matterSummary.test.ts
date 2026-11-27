import { describe, expect, it } from "vitest";
import { partReply, summaryFetcher, summaryUrl, type SummaryPart } from "./matterSummary";

function reply(status: number, body: unknown): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } }));
}

function ownUrl(part: SummaryPart, matterId: string): string {
  return `/api/clients/${part}?matter_id=${matterId}`;
}

async function askTogether(matterId: string, parts: SummaryPart[], fetchImpl: (url: string) => Promise<Response>) {
  const replies = parts.map((part) => summaryFetcher(matterId, part, fetchImpl)(ownUrl(part, matterId)));
  return Promise.all(replies.map(async (r) => {
    const res = await r;
    return { status: res.status, body: res.ok ? await res.json() : null };
  }));
}

describe("summaryFetcher", () => {
  it("sends reads asked at the same moment as one summary request and hands each its own part", async () => {
    const asked: string[] = [];
    const results = await askTogether("71", ["flags", "person_matters"], (url) => {
      asked.push(url);
      return reply(200, { matter_id: "71", flags: { flags: { starred: true } }, person_matters: { matters: [] }, errors: [] });
    });
    expect(asked).toEqual([summaryUrl("71", ["flags", "person_matters"])]);
    expect(results).toEqual([
      { status: 200, body: { flags: { starred: true } } },
      { status: 200, body: { matters: [] } },
    ]);
  });

  it("lets a read on its own ask its own route", async () => {
    const asked: string[] = [];
    await askTogether("72", ["flags"], (url) => {
      asked.push(url);
      return reply(200, {});
    });
    expect(asked).toEqual([ownUrl("flags", "72")]);
  });

  it("falls back to each read's own route when the summary request fails", async () => {
    const asked: string[] = [];
    const results = await askTogether("73", ["flags", "bill_of_costs"], (url) => {
      asked.push(url);
      return url.includes("matter-summary") ? reply(502, {}) : reply(200, { own: url });
    });
    expect(asked).toEqual([summaryUrl("73", ["flags", "bill_of_costs"]), ownUrl("flags", "73"), ownUrl("bill_of_costs", "73")]);
    expect(results.map((r) => r.body)).toEqual([{ own: ownUrl("flags", "73") }, { own: ownUrl("bill_of_costs", "73") }]);
  });

  it("falls back the same way when the summary request cannot be sent", async () => {
    const asked: string[] = [];
    const results = await askTogether("74", ["flags", "person_matters"], (url) => {
      asked.push(url);
      return url.includes("matter-summary") ? Promise.reject(new TypeError("offline")) : reply(200, { ok: 1 });
    });
    expect(asked).toHaveLength(3);
    expect(results.every((r) => r.status === 200)).toBe(true);
  });

  it("keeps separate matters apart", async () => {
    const asked: string[] = [];
    const fetchImpl = (url: string) => {
      asked.push(url);
      return reply(200, {});
    };
    await Promise.all([askTogether("75", ["flags"], fetchImpl), askTogether("76", ["person_matters"], fetchImpl)]);
    expect(asked.sort()).toEqual([ownUrl("flags", "75"), ownUrl("person_matters", "76")].sort());
  });
});

describe("partReply", () => {
  it("is a failed reply for a part the hub named in errors, and null for a part it did not send", () => {
    expect(partReply({ flags: null, errors: ["flags"] }, "flags")?.status).toBe(502);
    expect(partReply({ errors: [] }, "flags")).toBeNull();
    expect(partReply(null, "flags")).toBeNull();
  });
});
