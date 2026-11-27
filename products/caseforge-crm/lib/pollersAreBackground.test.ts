
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const read = (path: string) => readFileSync(fileURLToPath(new URL(path, import.meta.url)), "utf8");

describe("polls do not count as loading", () => {
  it("the header's five polls are one request, a background one", () => {
    expect(read("./pulse.ts")).toContain(`await backgroundFetch("/api/pulse"`);
    for (const file of ["useAttention.ts", "useFlagCounts.ts", "robotNotices.ts", "statementReplies.ts"]) {
      const src = read(`./${file}`);
      expect(src, file).toContain("createPulseSlice");
      expect(src, file).not.toContain("createPolledStore");
    }
  });

  it("the timer-driven hooks mark their re-read as silent", () => {
    expect(read("./todos.ts")).toMatch(/silentRef\.current = true;\s*refresh\(\);/);
    expect(read("./pipeline.ts")).toMatch(/silentRef\.current = true;\s*refresh\(\);/);
    expect(read("./fieldReviewQueue.ts")).toMatch(/silentRef\.current = true;\s*setPollTick/);
    expect(read("./todos.ts")).toContain("fetchTodos(queryRef.current, silent)");
  });

  it("the summary badge, the update check and the filing poll are background", () => {
    expect(read("./todos.ts")).toContain('await backgroundFetch("/api/todos/summary"');
    expect(read("../components/UpdateBanner.tsx")).toContain('await backgroundFetch("/api/version"');
    expect(read("../components/RecentAttendanceNotes.tsx")).toContain("void load(true)");
  });

  it("the filing poll stops when nothing is filing", () => {
    const src = read("../components/RecentAttendanceNotes.tsx");
    expect(src).toMatch(/if \(!anyFiling\) return;\s*return startVisiblePoll/);
  });
});
