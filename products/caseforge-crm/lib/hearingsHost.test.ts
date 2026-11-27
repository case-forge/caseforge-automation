import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { addDrawer, countBadge, createKey, editKey, hearingsHost, removeDrawer, updateEditDrawer } from "./hearingsHost";
import type { CreateSpec, DrawerEntry } from "./hearingsHost";
import { shouldCloseOnClick } from "../components/HearingSlideOut";
import { createPayloadFromForm, emptyFormValues } from "./hearings";
import type { Hearing } from "./hearings";
import { confirmLeaveUnsaved, setUnsaved } from "./unsavedEdits";

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8");
const hearing = (id: number): Hearing => ({ hearing_id: id, matter_id: 1, case_ref: `ZZ${id}`, client_name: "C", review_state: "ok" }) as unknown as Hearing;
const spec = (matterId: string, extra: Partial<CreateSpec> = {}): CreateSpec => ({ matterId, clientName: `Client ${matterId}`, defaults: { matter_id: matterId, case_ref: `REF${matterId}` }, ...extra });
const create = (s: CreateSpec): DrawerEntry => ({ key: createKey(s), kind: "create", spec: s });

describe("drawer identities", () => {
  it("one edit drawer per hearing, one create drawer per client", () => {
    expect(editKey({ hearing_id: 7 })).toBe("hearing-edit-7");
    expect(createKey({ matterId: "12" })).toBe("hearing-new:12");
    expect(createKey({ matterId: "", suffix: "manual" })).toBe("hearing-new:manual");
    expect(createKey({ matterId: "", suffix: "lead-3" })).toBe("hearing-new:lead-3");
    expect(createKey({ matterId: "12" })).not.toBe(createKey({ matterId: "13" }));
  });
});

describe("one drawer at a time", () => {
  const edit = (id: number, startEditing = false): DrawerEntry => ({ key: editKey(hearing(id)), kind: "edit", hearing: hearing(id), startEditing });
  it("opening a different hearing replaces the one showing: the list is only ever the new one", () => {
    const a = addDrawer([], create(spec("A")));
    const b = addDrawer(a.list, create(spec("B")));
    expect(b.list.map((d) => d.key)).toEqual(["hearing-new:B"]);
    expect(b.existed).toBe(false);
    expect(addDrawer(b.list, edit(1)).list.map((d) => d.key)).toEqual(["hearing-edit-1"]);
  });
  it("opening the one already showing keeps it, with its typing; an edit opened again may only add edit mode", () => {
    const first = addDrawer([], create(spec("A", { intro: "first" })));
    const again = addDrawer(first.list, create(spec("A", { intro: "second" })));
    expect(again.existed).toBe(true);
    expect(again.list[0]).toBe(first.list[0]);
    const viewing = addDrawer([], edit(2)).list;
    const editing = addDrawer(viewing, edit(2, true));
    expect(editing.list).toHaveLength(1);
    expect((editing.list[0] as { startEditing: boolean }).startEditing).toBe(true);
    expect((addDrawer(editing.list, edit(2, false)).list[0] as { startEditing: boolean }).startEditing).toBe(true);
  });
  it("closing removes it; a saved hearing replaces the one an edit drawer holds", () => {
    const list = addDrawer([], edit(1)).list;
    expect(removeDrawer(list, "hearing-edit-1")).toEqual([]);
    expect(removeDrawer(list, "nope")).toBe(list);
    const updated = updateEditDrawer(list, { ...hearing(1), court: "New Court" } as Hearing);
    expect((updated[0] as { hearing: Hearing }).hearing.court).toBe("New Court");
  });
});

describe("binding: a drawer saves for what it was opened for, never for the page that is open", () => {
  it("an Add a Hearing form opened for client A posts A's matter id, whatever client is open later", () => {
    const a = spec("12");
    const b = spec("13");

    const formA = emptyFormValues(a.defaults);
    const formB = emptyFormValues(b.defaults);

    expect(createPayloadFromForm({ ...formA, hearing_date: "2026-11-10" }).matter_id).toBe(12);
    expect(createPayloadFromForm({ ...formB, hearing_date: "2026-11-11" }).matter_id).toBe(13);
  });
  it("the drawer never reads the open client when it saves: only for the name shown in the unsaved-changes question", () => {
    const drawer = read("../components/HearingDrawer.tsx");
    const create = drawer.slice(drawer.indexOf("export function NewHearingDrawer"));
    expect(create).toContain("createPayloadFromForm(form)");
    expect(create).toContain("const matterId = defaults?.matter_id");

    expect(create).not.toContain("useCurrentClient()");
  });
  it("an edit drawer saves to its own hearing id", () => {
    const drawer = read("../components/HearingDrawer.tsx");
    expect(drawer).toContain("updateHearing(hearing.hearing_id");
  });
  it("every Add a Hearing button goes through the host, with the matter it is for", () => {
    expect(read("../components/MatterHearings.tsx")).toContain("matterId: String(matterId)");
    expect(read("../components/AttendanceNoteForm.tsx")).toContain("hearingsHost.openCreate({\n                matterId,");
    expect(read("../components/CalendarView.tsx")).toContain("hearingsHost.openCreate({");
    for (const file of ["MatterHearings", "CalendarView", "AttendanceNoteForm"]) {
      const code = read(`../components/${file}.tsx`);
      expect(code, file).not.toContain("<NewHearingDrawer");
      expect(code, file).not.toContain("<HearingDrawer");
    }
    expect(read("../components/AddHearingBox.tsx")).toContain("<NewHearingDrawer");
  });
});

describe("unsaved edits and leaving a page", () => {
  beforeEach(() => {
    setUnsaved("hearing-new:A", null);
    setUnsaved("client-edit", null);
  });
  it("leaving a page does not ask about a hosted drawer (it stays open); closing the drawer does", () => {
    const confirm = vi.fn(() => true);
    vi.stubGlobal("window", { confirm, addEventListener: () => undefined, removeEventListener: () => undefined });
    setUnsaved("hearing-new:A", { label: "New hearing", matterId: "A", persistent: true });
    expect(confirmLeaveUnsaved()).toBe(true);
    expect(confirm).not.toHaveBeenCalled();
    expect(confirmLeaveUnsaved(["hearing-new:A"])).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
  it("a client edit still asks when leaving, once, and the drawer is not counted in it", () => {
    const confirm = vi.fn(() => true);
    vi.stubGlobal("window", { confirm, addEventListener: () => undefined, removeEventListener: () => undefined });
    setUnsaved("hearing-new:A", { label: "New hearing", matterId: "A", persistent: true });
    setUnsaved("client-edit", { label: "Client details", matterId: "A" });
    expect(confirmLeaveUnsaved()).toBe(true);
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(String((confirm.mock.calls[0] as unknown[])[0])).toContain("Client details");
    expect(String((confirm.mock.calls[0] as unknown[])[0])).not.toContain("New hearing");
    vi.unstubAllGlobals();
  });
});

describe("the host", () => {
  it("an Add a Hearing form is a tab: the same client again shows its tab, another client gets another tab, and the slide-out is untouched", () => {
    hearingsHost.openCreate(spec("A"));
    hearingsHost.openCreate(spec("A"));
    expect(hearingsHost.tabs().tabs.map((t) => t.key)).toEqual(["hearing-new:A"]);
    hearingsHost.openCreate(spec("B"));
    expect(hearingsHost.tabs().tabs.map((t) => t.key)).toEqual(["hearing-new:A", "hearing-new:B"]);
    expect(hearingsHost.drawers()).toEqual([]);
    hearingsHost.closeDrawer("hearing-new:A");
    hearingsHost.closeDrawer("hearing-new:B");
    expect(hearingsHost.tabs().tabs).toEqual([]);
    hearingsHost.openEdit(hearing(5));
    hearingsHost.openEdit(hearing(5));
    hearingsHost.openEdit(hearing(6));
    expect(hearingsHost.drawers().map((d) => d.key)).toEqual(["hearing-edit-6"]);
    hearingsHost.closeDrawer("hearing-edit-5");
    expect(hearingsHost.drawers()).toHaveLength(1);
    hearingsHost.closeDrawer("hearing-edit-6");
    expect(hearingsHost.drawers()).toEqual([]);
  });
  it("the badge text is nothing at zero", () => {
    expect(countBadge(0)).toBe("");
    expect(countBadge(3)).toBe("3");
  });
});

describe("the one slide-out", () => {
  afterEach(() => {
    hearingsHost.requestClose();
  });
  it("opening a second hearing replaces the first: still one drawer, no tabs", () => {
    hearingsHost.openEdit(hearing(1));
    hearingsHost.openEdit(hearing(2));
    expect(hearingsHost.drawers().map((d) => d.key)).toEqual(["hearing-edit-2"]);
    hearingsHost.openCreate(spec("12"));

    expect(hearingsHost.drawers().map((d) => d.key)).toEqual(["hearing-edit-2"]);
    expect(hearingsHost.tabs().tabs.map((t) => t.key)).toEqual(["hearing-new:12"]);
    hearingsHost.closeTabNow("hearing-new:12");
  });
  it("the showing hearing is asked first: a hearing that says no stays open and the new one does not open", () => {
    hearingsHost.openEdit(hearing(1));
    const guard = vi.fn(() => false);
    const off = hearingsHost.registerGuard("hearing-edit-1", guard);
    hearingsHost.openEdit(hearing(2));
    expect(guard).toHaveBeenCalledTimes(1);
    expect(hearingsHost.drawers().map((d) => d.key)).toEqual(["hearing-edit-1"]);
    expect(hearingsHost.requestClose()).toBe(false);
    expect(hearingsHost.drawers()).toHaveLength(1);
    off();
    hearingsHost.openEdit(hearing(2));
    expect(hearingsHost.drawers().map((d) => d.key)).toEqual(["hearing-edit-2"]);
  });
  it("a hearing that agrees (it kept its work as a draft) is replaced, and closing from outside is the same question", () => {
    hearingsHost.openEdit(hearing(4));
    const kept = vi.fn(() => true);
    hearingsHost.registerGuard("hearing-edit-4", kept);
    hearingsHost.openEdit(hearing(5));
    expect(kept).toHaveBeenCalledTimes(1);
    expect(hearingsHost.drawers().map((d) => d.key)).toEqual(["hearing-edit-5"]);
    expect(hearingsHost.requestClose()).toBe(true);
    expect(hearingsHost.drawers()).toHaveLength(0);
  });
  it("a tab's X asks its form first (unfinished work goes to drafts) and a refusal keeps the tab", () => {
    hearingsHost.openCreate(spec("77"));
    const refuse = vi.fn(() => false);
    const off = hearingsHost.registerGuard("hearing-new:77", refuse);
    expect(hearingsHost.requestCloseTab("hearing-new:77")).toBe(false);
    expect(hearingsHost.tabs().tabs).toHaveLength(1);
    off();
    expect(hearingsHost.requestCloseTab("hearing-new:77")).toBe(true);
    expect(hearingsHost.tabs().tabs).toHaveLength(0);
  });
  it("opening the one already showing never asks", () => {
    hearingsHost.openEdit(hearing(1));
    const guard = vi.fn(() => false);
    const off = hearingsHost.registerGuard("hearing-edit-1", guard);
    hearingsHost.openEdit(hearing(1), { startEditing: true });
    expect(guard).not.toHaveBeenCalled();
    expect(hearingsHost.drawers()).toHaveLength(1);
    off();
  });
  it("a draft reopens in a tab, with its values", () => {
    hearingsHost.openDraft({ id: "d1", savedAt: "", matterId: "12", clientName: "A Client", values: { court: "Typed" } });
    const draft = hearingsHost.tabs().tabs.find((t) => t.key === "hearing-new:draft-d1")!;
    expect(draft.spec.restoreValues).toEqual({ court: "Typed" });
    expect(draft.spec.draftId).toBe("d1");
    hearingsHost.closeTabNow(draft.key);
  });
  it("the slide-out (edit) has no tab strip, ignores clicks in any floating box; closes by X, Escape and a click beside the panel", () => {
    const drawer = read("../components/HearingDrawer.tsx");
    expect(drawer).not.toContain("useFloatingBox");
    expect(drawer).not.toContain("createPortal");
    const slide = read("../components/HearingSlideOut.tsx");
    expect(slide).toContain(".fw,");
    expect(slide).not.toContain("hearing-slideout-backdrop");
    expect(slide).toContain("hearingsHost.requestClose()");
    expect(drawer).toContain('e.key !== "Escape"');
    expect(read("../components/GlobalHearings.tsx")).toContain("drawers.slice(0, 1)");
  });
  it("an unfinished NEW hearing is kept as a draft when replaced or closed, and the person is told; Save to drafts is on the form", () => {
    const create = read("../components/HearingDrawer.tsx");
    expect(create).toContain("Save to drafts");
    expect(create).toContain("hearingToast.show(");
    expect(create).toContain("hearingsHost.registerGuard(guardId, () => guard.current())");
    expect(create).toContain("if (draftId) deleteHearingDraft(draftId)");

    expect(create).toContain("hearingsHost.registerGuard(guardId, () => confirmLeaveUnsaved([guardId]))");
  });
});

describe("clicks on the page while a hearing is showing", () => {
  const base = { attemptsBefore: 3, attemptsNow: 3, connected: true, insideKept: false, eventTime: 500, mountedAt: 100 };
  it("a click on blank space closes it", () => {
    expect(shouldCloseOnClick(base)).toBe(true);
  });
  it("a click that asked to open a hearing never closes it: the hearing's own handler replaces it (even when the showing one said no)", () => {
    expect(shouldCloseOnClick({ ...base, attemptsNow: 4 })).toBe(false);
  });
  it("a click in the panel, the header, a dialog or a menu, on something already gone, or the one that opened the panel, never closes it", () => {
    expect(shouldCloseOnClick({ ...base, insideKept: true })).toBe(false);
    expect(shouldCloseOnClick({ ...base, connected: false })).toBe(false);
    expect(shouldCloseOnClick({ ...base, eventTime: 90 })).toBe(false);
  });
  it("every way of opening a hearing counts as an open request, so the page handler can tell", () => {
    const before = hearingsHost.openAttempts();
    hearingsHost.openEdit(hearing(1));
    hearingsHost.openCreate(spec("A"));
    hearingsHost.openDraft({ id: "x", savedAt: "", matterId: "", values: {} });
    expect(hearingsHost.openAttempts()).toBe(before + 3);
    hearingsHost.requestClose();
  });
});

describe("an empty day on the calendar", () => {
  it("only selects the day: nothing opens from it, and Add hearing starts on the selected day", () => {
    const view = read("../components/CalendarView.tsx");
    expect(view).toContain("onDateClick={(date, time) => setSelected({ date, time })}");
    expect(view).not.toMatch(/onDateClick=\{[^}]*openCreate/);
    expect(view).toContain("openCreate(selected ? { hearing_date: selected.date, hearing_time: selected.time ?? \"\" } : {})");
    expect(read("../components/CalendarGrid.tsx")).toContain("hearing-day--selected");
  });
  it("a click on an empty day is a blank click: it asks to open nothing, so it closes the panel", () => {

    const before = hearingsHost.openAttempts();
    expect(shouldCloseOnClick({ attemptsBefore: before, attemptsNow: hearingsHost.openAttempts(), connected: true, insideKept: false, eventTime: 2, mountedAt: 1 })).toBe(true);
  });
});

describe("a draft keeps its day", () => {
  it("the day and time stay with a draft even when they were prefilled from the selected day", () => {
    expect(read("../components/HearingDrawer.tsx")).toContain("...values, ...when");
  });
});
