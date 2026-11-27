
import type { ClientMatch } from "./types";
import { childrenOf, fullNameOf, hasC8 } from "./types";
import { normaliseOrderText } from "./orderText";

function extra(match: ClientMatch, key: string): string {
  const value = match.extra?.[key];
  return typeof value === "string" && value.trim().length > 0 ? value.trim() : "";
}

export function clientContextSummary(match: ClientMatch): string {
  const lines: string[] = [`Client: ${fullNameOf(match)}`];

  const matterBits = [match.matter_name, match.client_role].filter(Boolean).join(" - ");
  if (matterBits) lines.push(`Matter: ${matterBits}`);
  if (match.order_requested_text) lines.push(`Order sought: ${normaliseOrderText(match.order_requested_text)}`);
  if (match.live_matter_folder) lines.push(`Live folder: ${match.live_matter_folder}`);
  if (hasC8(match)) lines.push("C8 confidentiality flag is set - do not disclose contact details to the respondent.");

  const children = childrenOf(match);
  if (children) lines.push(`Children: ${children}`);

  const nextHearing = extra(match, "next_hearing_text");
  if (nextHearing) lines.push(`Next hearing: ${nextHearing}`);

  const awaitingNextStep = extra(match, "awaiting_next_step");
  if (awaitingNextStep) lines.push(`Awaiting next step: ${awaitingNextStep}`);

  const orderStatus = extra(match, "order_status");
  if (orderStatus) lines.push(`Order status: ${orderStatus}`);
  const sealedOrderStatus = extra(match, "sealed_order_status");
  if (sealedOrderStatus) lines.push(`Sealed order status: ${sealedOrderStatus}`);
  const draftOrderStatus = extra(match, "draft_order_status");
  if (draftOrderStatus) lines.push(`Draft order status: ${draftOrderStatus}`);
  const serviceStatus = extra(match, "service_status");
  if (serviceStatus) lines.push(`Service status: ${serviceStatus}`);

  const lastEmailSubject = extra(match, "last_material_email_subject");
  const lastEmailReceived = extra(match, "last_material_email_received");
  if (lastEmailSubject || lastEmailReceived) {
    lines.push(
      `Last material email: ${[lastEmailSubject, lastEmailReceived].filter(Boolean).join(" - ")}`,
    );
  }

  const legalAidStatus = match.legal_aid_tracker_status;
  if (legalAidStatus) lines.push(`Legal aid tracker status: ${legalAidStatus}`);

  return lines.join("\n");
}
