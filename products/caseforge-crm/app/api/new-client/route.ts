
import { NextRequest } from "next/server";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { editorFor } from "@/lib/editor";
import { hubGetJson, hubPostJson, isStubMode } from "@/lib/hubProxy";
import { stubAddPendingNewClient } from "@/lib/stubPendingNewClients";
import { cleanPhone } from "@/lib/newClient";
import { stubMakeClient } from "@/lib/stubClients";
import type { StubDetails } from "@/lib/stubClients";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const STUB_CATEGORIES = [
  { key: "nmo_cao", label: "NMO-CAO" },
  { key: "care_proceedings", label: "Care Proceedings" },
  { key: "immigration", label: "Immigration" },
];

export async function GET(request: NextRequest): Promise<Response> {
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;
  if (isStubMode()) return Response.json({ categories: STUB_CATEGORIES });
  return hubGetJson(request, "/client-viewer/new-client/categories", {}, remoteUser);
}

export async function POST(request: NextRequest): Promise<Response> {
  const crossSite = refuseCrossSiteWrite(request);
  if (crossSite) return crossSite;
  const { rejection, remoteUser } = await resolveIdentityForRoute(request.headers);
  if (rejection) return rejection;

  let payload: Record<string, unknown>;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: "malformed request body" }, { status: 400 });
  }
  const text = (key: string) => String(payload[key] ?? "").trim();
  const first = text("first_name");
  const last = text("last_name");
  const email = text("email");
  const category = text("category");
  const by = editorFor(remoteUser);
  if (!first || !last) return Response.json({ error: "Enter the client's first name and last name." }, { status: 400 });
  if (!email) return Response.json({ error: "Enter the client's email address." }, { status: 400 });
  if (!category) return Response.json({ error: "Choose a matter." }, { status: 400 });

  const phone = cleanPhone(payload.phone);
  if (!phone.ok) return Response.json({ error: phone.error }, { status: 400 });
  const preview = payload.preview === true;
  const sendRif = payload.send_rif === true;
  const sendLaif = payload.send_laif === true;
  if (isStubMode()) {

    const extras = [
      ...(sendRif ? ["Opponent Info Form"] : []),
      ...(sendLaif ? ["Legal Aid Info Form"] : []),
    ];
    const documents = ["New Client Form + Letter of Authority", ...extras].join(" + ");
    if (preview) {
      return Response.json({
        preview: true,
        category,
        folder: { path: `stub/${first} ${last}`, book: "stub", subfolders: [] },
        record: phone.value ? { people: { phone_primary: phone.value } } : {},
        envelopes: ["New Client Form + Letter of Authority", ...extras].map((name) => ({ documents: name, signer: email })),
        drafts: [{ documents, to: email, subject: "stub" }],
        billing: [],
      });
    }
    const extraKeys = [...(sendRif ? ["respondent"] : []), ...(sendLaif ? ["legal-aid"] : [])];
    const pendingId = stubAddPendingNewClient(`${first} ${last}`, email, category, extraKeys);

    const details = payload.stub_details && typeof payload.stub_details === "object" ? (payload.stub_details as StubDetails) : undefined;
    const made = stubMakeClient({ first, last, email, category, details });
    return Response.json({
      pending_id: pendingId,
      status: "pending",
      matter_id: made.matter_id,
      folder: "stub",
      category,
      drafts: [{ documents, web_link: "https://outlook.office.com/mail/drafts" }],
    });
  }

  const requestId = preview ? "" : text("request_id").slice(0, 64);
  return hubPostJson(
    request,
    preview ? "/client-viewer/new-client/preview" : "/client-viewer/new-client",
    {
      first_name: first,
      last_name: last,
      email,
      category,
      send_rif: sendRif,
      send_laif: sendLaif,
      address_checked: payload.address_checked === true,
      by,
      ...(phone.value ? { phone: phone.value } : {}),
      ...(requestId ? { request_id: requestId } : {}),
    },
    remoteUser,
  );
}
