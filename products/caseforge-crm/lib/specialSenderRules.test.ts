import { describe, expect, it } from "vitest";
import { domainMatches, matchSender, parseMark, parseSpecialSenders, senderInitials, senderLogoSrc } from "./specialSenderRules";
import type { SpecialSender } from "./specialSenderRules";

const sender = (over: Partial<SpecialSender> = {}): SpecialSender => ({ id: "ss_1", name: "Test Chambers", domains: ["chambers.example"], new_clients: false, logo: "", mark: null, ...over });

describe("domainMatches", () => {
  it("matches the domain and its subdomains, in any case", () => {
    expect(domainMatches("chambers.example", ["chambers.example"])).toBe(true);
    expect(domainMatches("Mail.Chambers.Example", ["chambers.example"])).toBe(true);
  });

  it("never matches a look-alike, an empty domain or an empty rule", () => {
    expect(domainMatches("notchambers.example", ["chambers.example"])).toBe(false);
    expect(domainMatches("chambers.example.evil.test", ["chambers.example"])).toBe(false);
    expect(domainMatches("", ["chambers.example"])).toBe(false);
    expect(domainMatches(undefined, ["chambers.example"])).toBe(false);
    expect(domainMatches("chambers.example", ["", "  "])).toBe(false);
  });
});

describe("matchSender", () => {
  const list = [sender(), sender({ id: "ss_2", name: "Test Referrer", domains: [], new_clients: true })];

  it("returns the first sender that matches, with its place in the list", () => {
    expect(matchSender(list, { senderDomain: "chambers.example" })).toMatchObject({ rank: 0, sender: { id: "ss_1" } });
    expect(matchSender(list, { newClient: true })).toMatchObject({ rank: 1, sender: { id: "ss_2" } });
  });

  it("matches nothing for an ordinary notification or an empty list", () => {
    expect(matchSender(list, { senderDomain: "other.example" })).toBeNull();
    expect(matchSender(list, { newClient: false })).toBeNull();
    expect(matchSender([], { senderDomain: "chambers.example", newClient: true })).toBeNull();
  });
});

describe("parseSpecialSenders and the badge helpers", () => {
  it("keeps well-formed senders, drops the rest and trusts only a hash for the logo", () => {
    const parsed = parseSpecialSenders({ items: [{ id: "a", name: "A", domains: ["x.example", 3], new_clients: true, logo: "ab12" }, { id: "", name: "No id" }, null, { id: "b", name: "B", logo: "../x" }] });
    expect(parsed).toEqual([
      { id: "a", name: "A", domains: ["x.example"], new_clients: true, logo: "ab12", mark: null },
      { id: "b", name: "B", domains: [], new_clients: false, logo: "", mark: null },
    ]);
    expect(parseSpecialSenders(null)).toEqual([]);
  });

  it("addresses a logo by hash, and has none for a sender without one", () => {
    expect(senderLogoSrc(sender({ logo: "ab12" }))).toBe("/api/settings/special-sender-logo?id=ss_1&v=ab12");
    expect(senderLogoSrc(sender())).toBe("");
  });

  it("makes initials for a sender with no logo", () => {
    expect(senderInitials("Test Chambers")).toBe("TC");
    expect(senderInitials("Solo")).toBe("SO");
    expect(senderInitials("  ")).toBe("?");
  });
});

describe("a made logo", () => {
  const good = { text: "DV", colours: ["#1e7a34", "#111111"], background: "#d4d4d4" };

  it("is letters with a six-digit colour each and a background, or nothing", () => {
    expect(parseMark(good)).toEqual(good);
    expect(parseMark(null)).toBeNull();
    expect(parseMark({ ...good, text: "DVAB", colours: ["#111111", "#111111", "#111111", "#111111"] })).toBeNull();
    expect(parseMark({ ...good, colours: ["#1e7a34"] })).toBeNull();
    expect(parseMark({ ...good, colours: ["red", "#111111"] })).toBeNull();
    expect(parseMark({ ...good, background: "grey" })).toBeNull();
    expect(parseMark({ ...good, text: "D!", colours: ["#111111", "#111111"] })).toBeNull();
  });

  it("comes through the parse with the sender", () => {
    expect(parseSpecialSenders({ items: [{ id: "a", name: "A", mark: good }, { id: "b", name: "B", mark: { text: "" } }] }).map((s) => s.mark)).toEqual([good, null]);
  });
});
