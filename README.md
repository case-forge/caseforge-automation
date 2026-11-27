# CaseForge Automation

Casework automation for UK family-law firms: a client and matter CRM, a step-by-step case pipeline from referral to closing letter, court-form filling, document drafting and a billing ledger, built on Microsoft 365, a self-hosted signing service and language models run under zero data retention.

It does casework administration and procedural support. It does not give legal advice, and nothing it produces leaves the firm without a person reading it and pressing send.

Copyright © 2026 CaseForge. Source-available under the Functional Source License 1.1 (MIT Future License); see [Licence](#licence).

## Who it is for

- Family-law firms in England and Wales, especially those doing domestic-abuse protective orders (non-molestation and occupation orders on the FL401) and children orders (C100 and C1A).
- Firms that already run on Microsoft 365: an Exchange mailbox for casework mail and a SharePoint or OneDrive library holding one folder per client.
- Developers and operators who can run Linux services, Postgres and a Next.js app, and are comfortable reading Python.

It is not a hosted product. You run it on your own server, against your own tenant.

## Features

- **CRM.** Search clients and matters, open a detail panel with tabs for the client, opponent, children, hearings, billing, tasks and Case flow, and edit single-value fields with every change attributed and logged. Fuzzy name search, same-name labels, a Today board, an attention bell and a drafts list.
- **Case flow.** About twenty numbered steps take a matter from referral to closing letter: fetch the referral papers, check the record, make the client folders, unpack attachments, prepare the witness statement, draft the client email with a signing envelope, make the court pack, draft the court email, file the court's reply, send papers to the client, request counsel, build the hearing bundle, arrange service, file and forward statements of service, make the client care letter and brief to counsel, and draft the court-outcome and closing letters. Each step has its own button. An auto mode can walk the chain, and it stops at the first step that needs a person.
- **Court forms.** Fills the FL401, C100 and C1A PDF forms from the matter record and the client's statement. Values a model suggests are checked in code against the source text, and anything not found there is dropped and listed for a person.
- **Documents.** Turns a client's witness statement into the firm's template, with the court heading built in code, numbering resolved and spelling checked by a small model behind a guard. Also makes Notices of Acting, draft orders, attendance notes, client care letters (with a linter and a source audit), briefs to counsel, case summaries, chronologies and hearing bundles.
- **Billing model.** A per-matter ledger with one row per chargeable event. Amounts are computed on the server from a fixed rate table and a caller cannot pass a price. Court documents and bundles are billed by their real page count, and an export validator checks the arithmetic.
- **Integrations.** Wrappers for Microsoft Graph (mail, files, change notifications), Documenso (signing envelopes) and OpenRouter (model calls), each with one entry point the rest of the code uses.
- **Firm profile.** One validated file describes the firm a deployment serves, so the code carries no firm names, domains or staff of its own.

## Architecture

```
            browser
               │  (optional Cloudflare Access in front)
               ▼
   CRM (Next.js, server-side routes)       holds the API token; the browser never does
               │  HTTPS + bearer token, Remote-User identity
               ▼
   Hub API (FastAPI, tools/vergil/api.py)  client-exposure audit, named actor on every write
      │            │              │               │
      ▼            ▼              ▼               ▼
  clientdb      ops DB        Microsoft Graph   Documenso
  (Postgres)    (SQLite)      mail, files       signing envelopes
      ▲            ▲              ▲
      │            │              │
   Workers on systemd services and timers ──► model_backend ──► OpenRouter (ZDR)
   (mail intake and triage, Case flow auto
    passes, filing, index refresh, backups)
```

- **Hub API.** One FastAPI service in front of the domain code. The CRM and the scripts go through it, so its rules (the exposure audit, write attribution, input checks) apply to every caller.
- **Workers.** Long-running queue workers and timed jobs, defined as systemd units in `deploy/systemd/` and scheduled through Ansible. A durable job queue lives in the ops database. Scheduled jobs ping a Healthchecks dead-man's switch, so a job that stops running raises an alert.
- **clientdb.** Postgres holds people, matters, parties, children, references, hearings and attention items. Every client-data table carries a change-log trigger.
- **ops DB.** SQLite holds workflow state: Case flow events, the billing ledger, flags, the job queue, the OneDrive catalogue and telemetry. It has its own change log.
- **Microsoft Graph.** Mail intake arrives by Graph change notification through an Azure Function and a storage queue that the server polls outbound, so nothing listens on a public port. Files are read and written in the firm's SharePoint or OneDrive library.
- **Documenso.** A self-hosted instance makes signing envelopes. It sends no email: signing links travel only inside a draft a person sends.
- **Models.** Every model call goes through `tools/model_backend.py`, by purpose role (`case_summary`, `mail_triage`, `safety_guard` and others, each set in `runtime-data/model-roles.env`) rather than model name. Calls go to OpenRouter with zero data retention asserted on every request (`provider.zdr=true`, `data_collection=deny`). A model with no compliant provider fails with an error and is never silently downgraded.

The subsystems are covered in more depth in [ARCHITECTURE.md](ARCHITECTURE.md).

## Getting started

**To see it working,** run the demo. It needs only Node.js, and it opens the CRM on built-in sample clients with the training game beside it:

```
cd products/caseforge-crm
npm run demo
```

**To deploy it** you need a Linux server, Python 3.11 or later, Node.js, Postgres and a Microsoft 365 tenant.

1. Install the Python requirements and the CRM's packages.
2. Describe your firm in a profile file, starting from the example in `profile/`.
3. Copy `.env.example` and fill in your own values. Keep secrets in a secrets manager, never in the repository.
4. Provision your servers with the Ansible playbook under `deploy/ansible/`, against your own inventory.
5. Run the test suite, then start the CRM. With no hub API configured it opens in demo mode on built-in sample data.

For deployment support or a guided setup, contact CaseForge.

## Safety design

Client data here belongs to people who are often at risk, many of them survivors of domestic abuse. The design assumes a mistake will happen and tries to make it visible and reversible.

- **Drafts only, never auto-send.** There is one function that creates mail (`graph_mail_safe_ops.post_draft_payload`). It creates a draft (`isDraft: true`) and never calls `sendMail`, and every draft is tagged `AI DRAFTED`. A draft whose subject, body or attachments still say "TBC" or "to be confirmed" is refused. Documenso envelopes are created with `sendEmail: false`. Auto mode makes drafts too and never sends.
- **Deterministic guards.** Code owns safety and scoping, and models only read and draft. A model never writes SQL. A form value a model suggests must appear in the source text or it is dropped. The client lookup returns `resolved`, `ambiguous` or `not_found` and never a bare best guess. Billing amounts come from a fixed rate table. Auto mode fails closed, so with no switch-on time recorded it runs for nobody. A folder book marked read-only is never written.
- **Client-exposure budget.** The hub API counts the distinct client records each identity is shown over a rolling 24 hours, per caller where the CRM passes a verified identity and in one shared pool otherwise. A large disclosure can be traced afterwards through the audit trail.
- **C8 handling.** When a client's contact details are confidential (form C8), the shared protection module empties the form's own contact boxes and replaces the client's address, postcode, phone and email with `Withheld - see C8` everywhere else. Case summaries redact once, at the point facts are read, so no renderer can leak a withheld value. A C8 form is never sent to the process server, and the court email uses a C8 variant of its template.
- **Change log on SQL.** A trigger on every client-data table writes the whole old and new row, the actor and the application to `clientdb_change_log`. The log refuses updates and deletes to itself, and if logging fails the write fails too. `tools/sql/change_log.py` shows entries and reverts them, as a dry run unless you pass `--apply`. The ops database keeps the same kind of log.
- **Untrusted input.** Emails, referrals and documents are treated as evidence, not instructions.

## Status and limitations

- This is an early release of a system in production use.
- The demo is the part that runs from this repository alone. The hub API and the workers load parts of the case pipeline that are not included yet, so a full deployment is a guided setup, not a clone and run.
- The firm's own letter, email and document templates are not included. `templates-general/` holds published court material, and you supply your own house templates.
- The hub API package is named `vergil`.
- Not every test in the source repository is included, so tests that depend on private templates or live data stay behind.
- Microsoft 365 is required: there is no other mail or file backend.
- Several values are firm-specific and still have defaults in code. Look at the profile loader's call sites before relying on a value you have not set.

## Licence

Copyright © 2026 CaseForge.

Licensed under the Functional Source License 1.1, MIT Future License (`FSL-1.1-MIT`); see `LICENSE` for the full text. The source is available, and you may use, modify and run it for any purpose except offering a competing commercial product or service. Each version becomes MIT-licensed two years after its release. It comes with no warranty.

Licensing enquiries, including other licence terms: CaseForge, caseforge.uk. Third-party components and their licences are listed in `NOTICE`.

See also [CONTRIBUTING.md](CONTRIBUTING.md) and [SECURITY.md](SECURITY.md).
