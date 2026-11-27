
import { createElement, Fragment } from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { emptyListMessage, highlightName } from "./ResultsList";

function render(name: string, query: string): string {
  return renderToStaticMarkup(createElement(Fragment, null, highlightName(name, query)));
}

describe("highlightName", () => {
  it("wraps the matched characters in <mark>", () => {
    const html = render("Mia Miketest", "mm");
    expect(html).toContain("<mark>M</mark>ia");
    expect(html).toContain("<mark>M</mark>iketest");
  });

  it("returns the plain name unchanged when the query is empty", () => {
    expect(render("Mia Miketest", "")).toBe("Mia Miketest");
    expect(render("Mia Miketest", "   ")).toBe("Mia Miketest");
  });

  it("falls back to the plain name when there is no match at all", () => {

    const html = render("Mia Miketest", "zzzzz9999");
    expect(html).toBe("Mia Miketest");
  });

  it("is case-insensitive, matching the fuzzy search behaviour it mirrors", () => {
    const html = render("Mia Miketest", "MIA");
    expect(html).toContain("<mark>");
  });
});

describe("emptyListMessage", () => {
  it("words each empty quick list as its own sentence", () => {
    expect(emptyListMessage("Frequent callers")).toBe("No frequent callers right now.");
    expect(emptyListMessage("Recently viewed")).toBe("No client recently viewed.");
  });

  it("falls back to the old form for a list it does not know", () => {
    expect(emptyListMessage("Some New List")).toBe("No one is some new list right now.");
  });
});
