
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubGetJson, isStubMode } from "@/lib/hubProxy";
import { stepRefCap } from "@/lib/pipelineTypes";

export const dynamic = "force-dynamic";

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) {

    const sec = (key: string, title: string, items: Record<string, unknown>[]) => ({ key, title, count: items.length, items, error: false });

    const tile = (matter_id: string, client_name: string, step: string, state: string, line: string, link: Record<string, string> | null, current: string, days: number) => ({
      matter_id, client_name, step, state, line, link: link ?? {}, at_step: { current, days, quiet: false }, checked_utc: "2026-11-03T08:00:00Z",
    });
    const stopped = ["client", "court", "counsel"].map((state) => ({ matter_id: `wait-${state}`, client_name: `Stub Waiting ${state}`, state, label: `WAITING FOR ${state.toUpperCase()}` }));
    const sections = [
      sec("step_3", `${stepRefCap("email")} (email first Witness Statement draft)`, [
        tile("stub-a", "Stub Firstdraft", "email", "yours", "The email to the client is drafted. Review it in Drafts and send it.", { kind: "draft", label: "Open the draft in Outlook", url: "https://outlook.example.invalid/draft-a" }, "Email drafted with the Documenso envelope", 1),
        tile("stub-b", "Stub Waitingtoday", "email", "flow", "Ready to draft the email with the statement.", null, "Email drafted with the Documenso envelope", 4),
        tile("stub-new", "Stub Newclient", "email", "flow", "New client.", null, "Client logged to database", 0),
      ]),
      sec("step_4", `${stepRefCap("amend")} (email amended Witness Statement draft)`, [
        tile("stub-c", "Stub Amended", "amend", "yours", "The amended statement is drafted. Review it in Drafts and send it.", { kind: "draft", label: "Open the draft in Outlook", url: "https://outlook.example.invalid/draft-c" }, "Client's changes to the statement, amended", 2),
      ]),
      sec("step_5", `${stepRefCap("ws_sign")} (email approved Witness Statement draft)`, [
        tile("stub-d", "Stub Approved", "ws_sign", "yours", "Approved by reply: send the approved statement to sign.", { kind: "draft", label: "Open the draft in Outlook", url: "https://outlook.example.invalid/draft-d" }, "Approved statement sent for signature", 7),
      ]),
      sec("step_6", `${stepRefCap("court_pack")} (check and sign applications and draft orders)`, [
        tile("stub-e", "Stub Formcheck", "court_pack", "yours", "The final forms are there. Press the forms are finished once you have checked them.", { kind: "folder", label: "Open the folder Preliminary-Docs-STUBE", url: "https://sharepoint.example.invalid/prelim-e" }, "Court pack ready", 1),
      ]),
      sec("step_7", `${stepRefCap("court_email")} (email applications to court)`, [
        tile("stub-f", "Stub Emailcourt", "court_email", "yours", "The application email is drafted. Review it in Drafts and send it.", { kind: "draft", label: "Open the draft in Outlook", url: "https://outlook.example.invalid/draft-f" }, "Application emailed to the court", 0),
        tile("stub-g", "Stub Portalcase", "court_email", "yours", "This court takes applications only through its online portal.", { kind: "portal", label: "Open the court's online portal (Example Portal Court)", url: "https://portal.example.invalid/login" }, "Application emailed to the court", 3),
      ]),
      sec("reminders", "Court chasers waiting to be sent", [{ matter_id: "stub-4", client_name: "Stub Chased", subject: "CT26F00000 || first party v second party || Application of 26 October 2026 - update requested", web_link: "https://outlook.office.com/mail/drafts" }]),
      sec("drafts", "Other drafts waiting for you", [{ matter_id: "stub-1", client_name: "Stub Drafted", subject: "CT26F00000 || first party v second party || application of 26 October 2026 - update requested", web_link: "https://outlook.office.com/mail/drafts" }]),
      sec("waiting_client", "Waiting for client", stopped.filter((r) => r.state === "client")),
      sec("waiting_court", "Waiting for court", stopped.filter((r) => r.state === "court")),
      sec("waiting_counsel", "Waiting for counsel", stopped.filter((r) => r.state === "counsel")),
    ];
    return Response.json({ today: "", tomorrow: "", sections });
  }
  return hubGetJson(request, "/client-viewer/today", {}, remoteUser);
}
