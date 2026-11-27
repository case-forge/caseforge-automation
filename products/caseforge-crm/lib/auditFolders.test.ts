import { describe, expect, it } from "vitest";
import type { ActorKind } from "./actorKind";
import { buildTree, carryPinned, flagKindsOf, folderPaths, groupOf, loadAuditFolders, placerOf, setFolderFlag, rollupSentence, rollupTotal, type FolderEvent, type FolderItem, type TreeNode } from "./auditFolders";

const ev = (kind: FolderEvent["kind"], who = "someone", action = "Uploaded"): FolderEvent => ({ at: "2026-11-10T09:00:00Z", kind, who, action, seen_by: ["ours"] });
const item = (path: string, extra: Partial<FolderItem> = {}): FolderItem => ({
  path, name: path.split("/").pop() ?? path, type: "file", modified: "", size: 1, indexed: true, removed: false, created: null, placed: null, edits: 0, last_edit: null, flags: {}, ...extra,
});
const all = { group: "all", onlyChanged: false, text: "", flagKinds: new Set<ActorKind>(), keep: new Set<string>() } as const;
const names = (node: TreeNode): string[] => node.children.map((c) => c.name);
const find = (node: TreeNode, path: string): TreeNode | undefined => (node.path === path ? node : node.children.map((c) => find(c, path)).find(Boolean));

describe("who put an item where it is", () => {
  it("is the last mover if there was one, otherwise the creator, otherwise nobody on record", () => {
    expect(placerOf(item("a", { created: ev("automation") }))?.kind).toBe("automation");
    expect(placerOf(item("a", { created: ev("automation"), placed: ev("person", "p", "Moved") }))?.kind).toBe("person");
    expect(groupOf(item("a"))).toBe("unrecorded");
    expect(groupOf(item("a", { created: ev("") }))).toBe("unrecorded");
  });
});

describe("buildTree", () => {
  const items = [
    item("Orders", { type: "folder" }),
    item("Orders/o.pdf", { created: ev("automation") }),
    item("Orders/p.pdf", { created: ev("automation"), placed: ev("person", "p", "Moved") }),
    item("Post/loose.pdf", { created: ev("agent") }),
    item("top.pdf"),
    item("Gone/x.pdf", { removed: true, indexed: false, removed_by: ev("person", "p", "Deleted") }),
  ];

  it("nests by path, folders first, and makes a folder for a path no folder item names", () => {
    const root = buildTree(items, all);
    expect(names(root)).toEqual(["Gone", "Orders", "Post", "top.pdf"]);
    expect(find(root, "Post")?.item).toBeNull();
  });

  it("rolls each folder up by who put its files where they are, and counts removals apart", () => {
    const root = buildTree(items, all);
    expect(find(root, "Orders")?.rollup).toEqual({ person: 1, agent: 0, automation: 1, unrecorded: 0 });
    expect(rollupTotal(root.rollup)).toBe(4);
    expect(root.removedBelow).toBe(1);
    expect(find(root, "Gone")?.rollup).toEqual({ person: 0, agent: 0, automation: 0, unrecorded: 0 });
  });

  it("keeps only one colour, with the folders that lead to it", () => {
    const root = buildTree(items, { ...all, group: "automation" });
    expect(names(root)).toEqual(["Orders"]);
    expect(names(root.children[0])).toEqual(["o.pdf"]);
  });

  it("counts a removed item under whoever removed it for the colour filter", () => {
    expect(names(buildTree(items, { ...all, group: "person" }))).toEqual(["Gone", "Orders"]);
  });

  it("drops items with nothing on record when asked, and filters by text in any case", () => {
    expect(find(buildTree(items, { ...all, onlyChanged: true }), "top.pdf")).toBeUndefined();
    expect(names(buildTree(items, { ...all, text: "LOOSE" }))).toEqual(["Post"]);
  });

  it("lists every folder path for collapse-all", () => {
    expect(folderPaths(buildTree(items, all)).sort()).toEqual(["Gone", "Orders", "Post"]);
  });
});

describe("flagged and clicked items", () => {
  const flag = { by: "admin", at: "2026-11-10T09:00:00Z", note: "" };
  const agentFlag = { by: "AI session", at: "2026-11-10T09:00:00Z", note: "not a statement" };
  const list = [
    item("a.pdf", { created: ev("person") }),
    item("b.pdf", { created: ev("automation"), flags: { person: flag } }),
    item("c.pdf", { created: ev("person") }),
    item("d.pdf", { created: ev("person"), flags: { agent: agentFlag } }),
  ];

  it("stay under a colour filter and under only-changes, which would otherwise drop them", () => {
    expect(names(buildTree(list, { ...all, group: "person" }))).toEqual(["a.pdf", "b.pdf", "c.pdf", "d.pdf"]);
    expect(names(buildTree([item("z.pdf", { flags: { person: flag } })], { ...all, onlyChanged: true }))).toEqual(["z.pdf"]);
    expect(names(buildTree(list, { ...all, group: "agent", keep: new Set(["c.pdf"]) }))).toEqual(["b.pdf", "c.pdf", "d.pdf"]);
  });

  it("are the only ones shown when a flag kind is chosen, each kind on its own, plus whatever was just clicked", () => {
    expect(names(buildTree(list, { ...all, flagKinds: new Set<ActorKind>(["person"]) }))).toEqual(["b.pdf"]);
    expect(names(buildTree(list, { ...all, flagKinds: new Set<ActorKind>(["agent"]) }))).toEqual(["d.pdf"]);
    expect(names(buildTree(list, { ...all, flagKinds: new Set<ActorKind>(["person", "agent"]) }))).toEqual(["b.pdf", "d.pdf"]);
    expect(names(buildTree(list, { ...all, flagKinds: new Set<ActorKind>(["automation"]), keep: new Set(["a.pdf"]) }))).toEqual(["a.pdf"]);
  });

  it("still obey the file name search", () => {
    expect(names(buildTree(list, { ...all, text: "a.pdf" }))).toEqual(["a.pdf"]);
  });

  it("list the kinds that flagged an item in a fixed order", () => {
    expect(flagKindsOf(item("x", { flags: { automation: agentFlag, person: flag, agent: agentFlag } }))).toEqual(["person", "agent", "automation"]);
    expect(flagKindsOf(item("x"))).toEqual([]);
  });
});

describe("carryPinned", () => {
  it("keeps a clicked item the newest answer lost, marked stale, and nothing else", () => {
    const before = [item("a.pdf"), item("b.pdf"), item("c.pdf")];
    const after = [item("a.pdf")];
    const got = carryPinned(before, after, new Set(["b.pdf"]));
    expect(got.map((i) => [i.path, i.stale ?? false])).toEqual([["a.pdf", false], ["b.pdf", true]]);
    expect(carryPinned(before, after, new Set())).toBe(after);
    expect(carryPinned(before, [...after, item("B.PDF")], new Set(["b.pdf"])).length).toBe(2);
  });
});

describe("rollupSentence", () => {
  it("reads in a fixed order and says so when empty", () => {
    expect(rollupSentence({ person: 1, agent: 0, automation: 3, unrecorded: 2 })).toBe("1 put there by people, 3 by automation, 2 with no record");
    expect(rollupSentence({ person: 0, agent: 0, automation: 0, unrecorded: 0 })).toBe("Nothing here");
  });
});

describe("setFolderFlag", () => {
  it("posts the client, path, type and the new state, and says whether it was taken", async () => {
    let sent: { url: string; init: RequestInit } | null = null;
    const ok = ((url: string, init: RequestInit) => {
      sent = { url, init };
      return Promise.resolve(new Response("{}"));
    }) as unknown as typeof fetch;
    expect(await setFolderFlag("Client One", { path: "Post/x.pdf", type: "file" }, true, ok)).toBe(true);
    expect(sent!.url).toBe("/api/audit-folders/flag");
    expect(JSON.parse(String(sent!.init.body))).toEqual({ client: "Client One", path: "Post/x.pdf", type: "file", flagged: true });
    expect(await setFolderFlag("c", { path: "p", type: "file" }, false, (() => Promise.resolve(new Response("{}", { status: 422 }))) as unknown as typeof fetch)).toBe(false);
    expect(await setFolderFlag("c", { path: "p", type: "file" }, false, (() => Promise.reject(new Error("x"))) as unknown as typeof fetch)).toBe(false);
  });
});

describe("loadAuditFolders", () => {
  const answer = (status: number, body: unknown = {}) => (() => Promise.resolve(new Response(JSON.stringify(body), { status }))) as unknown as typeof fetch;

  it("asks for the folder and the window, and reads a 403 as hidden and any other failure as an error", async () => {
    let asked = "";
    const spy = ((url: string) => {
      asked = url;
      return Promise.resolve(new Response("{}"));
    }) as unknown as typeof fetch;
    expect((await loadAuditFolders("Client One", 90, spy)).state).toBe("ok");
    expect(asked).toBe("/api/audit-folders?days=90&folder=Client+One");
    expect((await loadAuditFolders("", 30, answer(403))).state).toBe("hidden");
    expect((await loadAuditFolders("", 30, answer(502))).state).toBe("error");
    expect((await loadAuditFolders("", 30, (() => Promise.reject(new Error("x"))) as unknown as typeof fetch)).state).toBe("error");
  });
});
