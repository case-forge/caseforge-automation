
import { NextRequest } from "next/server";
import { editorFor } from "@/lib/editor";
import { resolveIdentityForRoute } from "@/lib/accessIdentity";
import { hubPostJson, isStubMode } from "@/lib/hubProxy";
import { cleanPhone } from "@/lib/newClient";
import { stubMakeClient } from "@/lib/stubClients";
import { refuseCrossSiteWrite } from "@/lib/writeGuard";

export const dynamic = "force-dynamic";

const STUB_LABELS: Record<string, string> = { nmo_cao: "NMO-CAO", care_proceedings: "Care Proceedings", immigration: "Immigration" };

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
  if (!category) return Response.json({ error: "Choose a matter." }, { status: 400 });
  const phone = cleanPhone(payload.phone);
  if (!phone.ok) return Response.json({ error: phone.error }, { status: 400 });

  const detailKeys = ["middle_name", "dob", "nino", "address_line1", "address_line2", "address_line3", "address_line4", "postcode", "matter_details"];
  const details: Record<string, string> = {};
  for (const key of detailKeys) {
    const value = String(payload[key] ?? "").replace(/\s+/g, " ").trim();
    if (value) details[key] = value;
  }
  const preview = payload.preview === true;

  if (isStubMode()) {
    if (preview) {
      return Response.json({
        preview: true,
        manual: true,
        category: STUB_LABELS[category] ?? category,
        folder: { path: `stub/${first} ${last}`, book: "stub", subfolders: [] },
        record: {
          people: {
            canonical_name: `${first} ${last}`,
            ...(email ? { email_primary: email } : {}),
            ...(phone.value ? { phone_primary: phone.value } : {}),
            ...(details.middle_name ? { name_middle: details.middle_name } : {}),
            ...(details.dob ? { dob_iso: details.dob } : {}),
            ...(details.nino ? { nino_canonical: details.nino.replace(/\s/g, "").toUpperCase() } : {}),
            ...Object.fromEntries([1, 2, 3, 4].filter((n) => details[`address_line${n}`]).map((n) => [`address_line${n}`, details[`address_line${n}`]])),
            ...(details.postcode ? { address_postcode: details.postcode.toUpperCase() } : {}),
          },
          matters: details.matter_details ? { tracker_notes: `Added manually in the CRM\nAdded manually, matter details: ${details.matter_details}` } : {},
        },
        envelopes: [],
        drafts: [],
        billing: [],
      });
    }
    const made = stubMakeClient({ first, last, email, category });
    return Response.json({ created: true, matter_id: made.matter_id, category: STUB_LABELS[category] ?? category, folder: "stub" });
  }

  return hubPostJson(
    request,
    preview ? "/client-viewer/new-client/manual/preview" : "/client-viewer/new-client/manual",
    {
      first_name: first,
      last_name: last,
      category,
      by,
      address_checked: payload.address_checked === true,
      ...(email ? { email } : {}),
      ...(phone.value ? { phone: phone.value } : {}),
      ...details,
    },
    remoteUser,
  );
}
