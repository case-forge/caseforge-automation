import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const card = readFileSync(fileURLToPath(new URL("./MailEmailCard.tsx", import.meta.url)), "utf8");

describe("the full labelling page's email card", () => {
  it("shows From, To, Cc when there is one, and Subject, so an outbound email reads right", () => {
    expect(card).toContain("<dt>From</dt><dd>{item.from}</dd>");
    expect(card).toContain("<dt>To</dt><dd>{item.to}</dd>");
    expect(card).toContain("{item.cc && (");
    expect(card).toContain("<dt>Subject</dt><dd>{item.subject}</dd>");
  });
});
