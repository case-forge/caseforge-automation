
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const read = (name: string) => readFileSync(join(__dirname, name), "utf8");

describe("Special senders panel", () => {
  const panel = read("SpecialSendersPanel.tsx");

  it("makes a logo from letters, a colour for each letter and a background, with the picture upload as the other choice", () => {
    expect(panel).toContain("Make letters");
    expect(panel).toContain("Picture");
    expect(panel).toContain('type="color"');
    expect(panel).toContain("Colour of the letter");
    expect(panel).toContain("Background colour");
    expect(panel).toContain("Upload a picture");
    expect(panel).toContain("MAX_MARK_LETTERS");
  });

  it("previews the draft in the row's own badge and sends the made logo with Save", () => {
    expect(panel).toContain("mark: row.mark");
    expect(panel).toContain("<SpecialSenderBadge");
  });

  it("is in no way specific to any one sender: it names no domain, and the list comes from the hub", () => {
    expect(panel).not.toMatch(/\b[a-z0-9-]+\.(com|co\.uk|org|uk)\b/i);
    expect(panel).toContain("fetchSpecialSenders");
  });
});

describe("the badge", () => {
  const badge = read("SenderBadge.tsx");

  it("draws the uploaded picture first, then the made logo letter by letter in its colours, then the initials", () => {
    expect(badge.indexOf("senderLogoSrc(sender)")).toBeLessThan(badge.indexOf("sender.mark"));
    expect(badge.indexOf("sender.mark")).toBeLessThan(badge.indexOf("senderInitials(sender.name)"));
    expect(badge).toContain("color: mark.colours[i]");
    expect(badge).toContain("background: mark.background");
  });
});
