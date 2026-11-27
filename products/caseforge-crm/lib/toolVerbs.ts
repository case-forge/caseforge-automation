
const TOOL_VERBS: Record<string, string> = {
  search_clients: "Looking up the client",
  retrieve_matter_context: "Checking the case files",
  check_letter_coverage: "Checking letter coverage",
  list_matter_folder: "Looking in the OneDrive folder",
  convert_document_to_pdf: "Converting the document to PDF",
  list_email_templates: "Checking email templates",
  read_email_template: "Reading an email template",
  create_mail_draft: "Drafting the email",
  attach_document_to_draft: "Attaching the document",
  resolve_known_recipient: "Looking up the recipient",
  resolve_chambers_email: "Looking up chambers' email",
  find_recipient_candidates: "Looking up the recipient",
  check_documenso_envelope_status: "Checking the signing status",
  create_documenso_signing_envelope: "Preparing the document for signing",
  create_multi_document_documenso_envelope: "Preparing the documents for signing",
  lint_ccl: "Checking the client care letter",
  audit_ccl_sources: "Checking the client care letter",
  get_job_status: "Checking the job status",
  list_recent_jobs: "Checking recent jobs",
  list_job_events: "Checking job history",
  list_job_artifacts: "Checking job files",
  check_ops_health: "Checking system health",
  check_tunnel_health: "Checking system health",
  check_model_health: "Checking system health",
  check_openrouter_spend: "Checking system health",
  check_llamacpp_health: "Checking system health",
};

const FALLBACK_VERB = "Working";

function bareName(name: string): string {
  const parts = String(name || "").split("__");
  return parts[parts.length - 1] || "";
}

export function verbFor(name: string): string {
  const bare = bareName(name);
  if (!bare) return FALLBACK_VERB;
  const known = TOOL_VERBS[bare];
  if (known) return known;
  const readable = bare.replace(/_/g, " ").trim();
  if (!readable) return FALLBACK_VERB;
  return readable.charAt(0).toUpperCase() + readable.slice(1);
}
