
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubIdentityHeaders } from "@/lib/hubProxy";
import { stubCreateAttendanceNote } from "@/lib/stub";
import { ATTENDANCE_CALLERS, ATTENDANCE_CREATE_KINDS, MAX_TIME_MINUTES, isAttendanceCreateKind, takesPages } from "@/lib/types";
import type { AttendanceNoteCreateResponse } from "@/lib/types";
import { CUSTOM_FOLDER_MAX, DOC_KINDS, DOC_OTHER_MAX, otherFolderKind } from "@/lib/anFolder";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) {
    return rejection;
  }

  let payload: {
    matter_id?: string;
    caller?: string;
    caller_other?: string;
    note_text?: string;
    time_minutes?: unknown;
    kind?: unknown;
    pages?: unknown;
    doc_kind?: unknown;
    doc_other?: unknown;
    attendance_folder?: unknown;
  };
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const matterId = (payload.matter_id ?? "").trim();
  if (!matterId) {
    return Response.json({ error: "matter_id is required" }, { status: 400 });
  }
  const noteText = (payload.note_text ?? "").trim();
  if (!noteText) {
    return Response.json({ error: "the note is empty" }, { status: 400 });
  }

  const kind = payload.kind === undefined || payload.kind === null || payload.kind === "" ? "call" : payload.kind;
  if (!isAttendanceCreateKind(kind)) {
    return Response.json({ error: `kind must be ${ATTENDANCE_CREATE_KINDS.join(", ")}` }, { status: 400 });
  }

  const caller = (payload.caller ?? "").trim();
  if (!(takesPages(kind) && caller === "") && !(ATTENDANCE_CALLERS as readonly string[]).includes(caller)) {
    return Response.json({ error: "the party must be court, counsel, client, respondent or other" }, { status: 400 });
  }
  const callerOther = (payload.caller_other ?? "").trim();
  if (caller === "other" && !callerOther) {
    return Response.json({ error: "say who the party was" }, { status: 400 });
  }

  let timeMinutes: number | null = null;
  if (payload.time_minutes !== undefined && payload.time_minutes !== null) {
    const n = payload.time_minutes;
    if (typeof n !== "number" || !Number.isInteger(n) || n < 1 || n > MAX_TIME_MINUTES) {
      return Response.json({ error: `time spent must be a whole number of minutes, 1 to ${MAX_TIME_MINUTES}` }, { status: 400 });
    }
    timeMinutes = n;
  }

  let pages: number | null = null;
  if (payload.pages !== undefined && payload.pages !== null && payload.pages !== "") {
    const n = payload.pages;
    if (typeof n !== "number" || !Number.isInteger(n) || n < 1 || n > 5000) {
      return Response.json({ error: "pages must be a whole number, 1 to 5000" }, { status: 400 });
    }
    pages = n;
  }

  const docKind = takesPages(kind) && typeof payload.doc_kind === "string" && DOC_KINDS.some((d) => d.value === payload.doc_kind) ? payload.doc_kind : null;

  const docOther = docKind === "other" && typeof payload.doc_other === "string" ? payload.doc_other.replace(/\s+/g, " ").trim().slice(0, DOC_OTHER_MAX) : "";

  const attendanceFolder = typeof payload.attendance_folder === "string" ? payload.attendance_folder.replace(/\s+/g, " ").trim().slice(0, CUSTOM_FOLDER_MAX) : "";
  if (attendanceFolder === "" || otherFolderKind(attendanceFolder) === "") {
    return Response.json({ error: "Choose an attendance notes folder: FLA, CA or Other." }, { status: 400 });
  }

  if (process.env.CASEFORGE_HUB_API_STUB === "1") {
    return Response.json(stubCreateAttendanceNote(matterId, caller, noteText, kind), { status: 202 });
  }

  const hubUrl = process.env.CASEFORGE_HUB_API_URL;
  const token = process.env.CASEFORGE_CHAT_API_TOKEN;
  if (!hubUrl || !token) {
    return Response.json(
      { error: "CASEFORGE_HUB_API_URL/CASEFORGE_CHAT_API_TOKEN not configured on the server" },
      { status: 503 },
    );
  }

  let upstream: Response;
  try {
    upstream = await fetch(new URL("/client-viewer/attendance-notes/create", hubUrl), {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, ...(await hubIdentityHeaders(request, remoteUser)), "Content-Type": "application/json" },
      body: JSON.stringify({
        matter_id: matterId,
        ...(caller ? { caller } : {}),
        caller_other: caller === "other" ? callerOther : "",
        note_text: noteText,
        ...(kind !== "call" ? { kind } : {}),
        ...(timeMinutes !== null ? { time_minutes: timeMinutes } : {}),
        ...(takesPages(kind) && pages !== null ? { pages } : {}),
        ...(docKind ? { doc_kind: docKind } : {}),
        ...(docOther ? { doc_other: docOther } : {}),
        ...(attendanceFolder ? { attendance_folder: attendanceFolder } : {}),
      }),
      signal: request.signal,
      cache: "no-store",
    });
  } catch {
    return Response.json({ error: "upstream request failed" }, { status: 502 });
  }

  if (!upstream.ok) {
    let message = "upstream request failed";
    try {
      const errBody = await upstream.json();
      if (typeof errBody?.detail === "string") message = errBody.detail;
    } catch {

    }
    return Response.json({ error: message }, { status: upstream.status });
  }

  let body: AttendanceNoteCreateResponse;
  try {
    body = await upstream.json();
  } catch {
    return Response.json({ error: "upstream returned a malformed response" }, { status: 502 });
  }
  return Response.json(body, { status: 202 });
}
