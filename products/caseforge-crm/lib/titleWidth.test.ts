import { describe, expect, it } from "vitest";
import { minWidthFor } from "./titleWidth";

const measure = (text: string) => text.length * 7;
const base = { font: "600 15px sans-serif", gap: 8, padding: 24, border: 2, measure };

describe("a window's minimum width", () => {
  it("is the full title, the buttons, the gaps, the padding and the border, worked out from the text", () => {
    const need = minWidthFor({ ...base, titleText: "Help improve email classifier", otherWidths: [80] });
    expect(need).toBe(Math.ceil(29 * 7 + 80 + 8 + 24 + 2));
  });
  it("grows with a longer title and with extras, and never ignores the buttons", () => {
    const short = minWidthFor({ ...base, titleText: "What's New", otherWidths: [80] });
    const long = minWidthFor({ ...base, titleText: "Help improve email classifier", otherWidths: [80] });
    const withBadge = minWidthFor({ ...base, titleText: "Upcoming Hearings", otherWidths: [24, 80] });
    expect(long).toBeGreaterThan(short);
    expect(withBadge).toBeGreaterThan(minWidthFor({ ...base, titleText: "Upcoming Hearings", otherWidths: [80] }));
    expect(short).toBeGreaterThan(80);
  });
});
