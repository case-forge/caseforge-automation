
import type { RobotNotice } from "./robotNotices";
import { DEMO_FIRM } from "./stubFirm";

const DAY = 86_400_000;
const notices: RobotNotice[] = [
  {
    notice_id: "stub-robot-old-1",
    kind: "attendance_note_failed",
    title: "Attendance note not filed",
    detail: "An older notice, past the panel's cap: it is on the Notification board.",
    matter_id: "9001",
    client_name: "Stub Testperson",
    created_utc: new Date(Date.now() - 9 * DAY).toISOString(),
  },
  {
    notice_id: "stub-robot-old-2",
    kind: "attendance_note_unsorted",
    title: "Attendance note filed to Unsorted",
    detail: "Another older notice, past the panel's cap.",
    matter_id: "9003",
    client_name: "Third Stubperson",
    created_utc: new Date(Date.now() - 5 * DAY).toISOString(),
  },
  {
    notice_id: "stub-robot-1",
    kind: "attendance_note_failed",
    title: "Attendance note not filed",
    detail: "matter 9001 has no live attendance-note folder yet. The note is saved: open the client, then Edit or Try again.",
    matter_id: "9001",
    client_name: "Stub Testperson",
    created_utc: new Date(Date.now() - 20 * 60_000).toISOString(),
  },
  {
    notice_id: "stub-robot-2",
    kind: "attendance_note_unsorted",
    title: "Attendance note filed to Unsorted",
    detail: `Third Stubperson has no attendance-notes folder, so the note is in '${DEMO_FIRM.folders.unsorted_notes}'. It moves into the client's folder by itself once there is one.`,
    matter_id: "9003",
    client_name: "Third Stubperson",
    created_utc: new Date(Date.now() - 5 * 60_000).toISOString(),
  },
  {
    notice_id: "stub-robot-block-1",
    kind: "caseflow_step_blocked",
    title: "Case flow is stuck at the email step (CF-STMT-01)",
    detail:
      "The witness statement still has placeholder text in it, usually the court heading (IN THE XXX FAMILY COURT) because the court was never set. Set the court on the client record, or press Clean statement on the Case flow tab: it looks the court up from the client's postcode. Then the email step goes on.",
    matter_id: "9002",
    client_name: "Second Stubperson",
    created_utc: new Date(Date.now() - 35 * 60_000).toISOString(),
  },
  {
    notice_id: "stub-robot-block-2",
    kind: "caseflow_step_blocked",
    title: "Case flow is stuck at the statement step (CF-STMT-02)",
    detail:
      "A person saved the statement as WS.SURNAME.docx and Case flow has not cleaned it, so it still has the referrer layout and heading. Press Clean statement on the Case flow tab. The person's copy is kept as WS.SURNAME.before-clean.docx first; nothing is replaced without it.",
    matter_id: "9004",
    client_name: "Fourth Stubperson",
    created_utc: new Date(Date.now() - 50 * 60_000).toISOString(),
  },
  {
    notice_id: "stub-robot-job-1",
    kind: "job_blocked",
    title: "A signed document has no client attached (JOB-SIGN-01)",
    detail:
      "Documenso document 237: Stubperson-Final-WS.pdf. A document was signed in Documenso but it carries no matter number and could not be matched to a client by its signer, so it has not been filed. Open it in Documenso, find whose it is and save it in that client's folder by hand. Dismiss this notice when it is filed.",
    matter_id: "",
    client_name: "",
    created_utc: new Date(Date.now() - 10 * 60_000).toISOString(),
  },
];

export function stubRobotNotices(): { count: number; items: RobotNotice[] } {
  return { count: notices.length, items: [...notices].reverse() };
}

export function stubDismissRobotNotice(noticeId: string): { count: number; items: RobotNotice[] } {
  const index = notices.findIndex((n) => n.notice_id === noticeId);
  if (index >= 0) notices.splice(index, 1);
  return stubRobotNotices();
}

export function stubAddRobotNotice(notice: { kind: string; title: string; detail: string; matter_id: string; client_name: string }): { count: number; items: RobotNotice[] } {
  notices.push({ ...notice, notice_id: `stub-robot-${Date.now()}-${notices.length}`, created_utc: new Date().toISOString() });
  return stubRobotNotices();
}
