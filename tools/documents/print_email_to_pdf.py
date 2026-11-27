#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Sequence


_TOOLS_DIR = Path(__file__).resolve().parent.parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from graph_mail_safe_ops import GRAPH_BASE, GraphClient, _must
import graph_files


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
TOOLS_DIR = REPO_ROOT / "tools"


def _bootstrap_val_env() -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from env_bootstrap import load_repo_secrets

        load_repo_secrets()
    except Exception:
        pass

def parse_args() -> argparse.Namespace:
    _bootstrap_val_env()
    parser = argparse.ArgumentParser(description="Render an Outlook message to PDF through Graph.")
    parser.add_argument("--message-id", required=True)
    parser.add_argument("--output", required=True, help="Local PDF output path.")
    parser.add_argument("--matter-id", default="", help="Matter id for allow_email_print gate.")
    parser.add_argument("--skip-permission-check", action="store_true")
    parser.add_argument("--no-cover", action="store_true", help="Do not add the CaseForge metadata header.")
    parser.add_argument("--tenant-id", default=os.getenv("GRAPH_TENANT_ID", ""))
    parser.add_argument("--client-id", default=os.getenv("GRAPH_MAIL_CLIENT_ID", os.getenv("GRAPH_CLIENT_ID", "")))
    parser.add_argument(
        "--client-secret",
        default=os.getenv("GRAPH_MAIL_CLIENT_SECRET", os.getenv("GRAPH_CLIENT_SECRET", "")),
    )
    parser.add_argument("--mailbox-upn", default=os.getenv("GRAPH_MAILBOX_UPN", ""))
    parser.add_argument("--max-retries", type=int, default=5)
    parser.add_argument("--retry-base-seconds", type=float, default=0.8)
    parser.add_argument("--metadata-json", default="", help="Optional path for print metadata JSON.")
    return parser.parse_args()


def graph_bytes(
    method: str,
    url: str,
    access_token: str,
    *,
    body: bytes | None = None,
    content_type: str = "application/octet-stream",
    timeout: int = 120,
    expected: Sequence[int] = (200, 201, 202, 204),
) -> tuple[int, bytes, dict[str, str]]:
    headers = {"Authorization": f"Bearer {access_token}"}
    if body is not None:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(url, headers=headers, data=body, method=method.upper())
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.status not in expected:
                raise RuntimeError(f"Graph {method} {url} returned HTTP {resp.status}: {raw[:300]!r}")
            return resp.status, raw, dict(resp.headers.items())
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        if exc.code in expected:
            return exc.code, raw, dict(exc.headers.items())
        raise RuntimeError(f"Graph {method} {url} returned HTTP {exc.code}: {raw[:600].decode('utf-8', 'replace')}") from exc


def graph_json(method: str, url: str, access_token: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
    raw_body = json.dumps(body).encode("utf-8") if body is not None else None
    _, raw, _ = graph_bytes(method, url, access_token, body=raw_body, content_type="application/json")
    if not raw:
        return {}
    return json.loads(raw.decode("utf-8"))


def ensure_email_print_allowed(matter_id: str) -> None:
    matter = str(matter_id or "").strip()
    if not matter:
        raise SystemExit("--matter-id is required unless --skip-permission-check is used.")
    if str(TOOLS_DIR) not in sys.path:
        sys.path.insert(0, str(TOOLS_DIR))
    from clientdb_sql import get_email_print_permission

    if get_email_print_permission(matter) is False:
        raise SystemExit(f"Email print blocked: matter_permissions.allow_email_print is switched off for {matter}.")


def mailbox_url(mailbox_upn: str, suffix: str) -> str:
    return f"{GRAPH_BASE}/users/{urllib.parse.quote(mailbox_upn, safe='@')}{suffix}"


def fetch_message_metadata(client: GraphClient, message_id: str) -> dict[str, Any]:
    return client.graph(
        "GET",
        client.mailbox_path(f"/messages/{urllib.parse.quote(message_id, safe='')}"),
        params={
            "$select": (
                "id,subject,receivedDateTime,sentDateTime,from,sender,toRecipients,ccRecipients,"
                "bccRecipients,hasAttachments,internetMessageId,conversationId,webLink,body"
            )
        },
        extra_headers={"Prefer": 'outlook.body-content-type="html"'},
    )


def fetch_message_mime(mailbox_upn: str, message_id: str, access_token: str) -> bytes:
    quoted = urllib.parse.quote(message_id, safe="")
    url = mailbox_url(mailbox_upn, f"/messages/{quoted}/$value")
    _, raw, _ = graph_bytes("GET", url, access_token)
    if not raw:
        raise RuntimeError("Graph returned an empty MIME payload.")
    return raw


def ensure_temp_folder(mailbox_upn: str, access_token: str) -> None:
    base = mailbox_url(mailbox_upn, "/drive/root:/Temp")
    try:
        graph_bytes("GET", base, access_token)
        return
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
    graph_json(
        "POST",
        mailbox_url(mailbox_upn, "/drive/root/children"),
        access_token,
        body={"name": "Temp", "folder": {}, "@microsoft.graph.conflictBehavior": "replace"},
    )


def upload_temp_bytes(mailbox_upn: str, access_token: str, suffix: str, data: bytes) -> dict[str, Any]:
    ensure_temp_folder(mailbox_upn, access_token)
    name = f"caseforge-email-print-{uuid.uuid4().hex}{suffix}"
    encoded = urllib.parse.quote(f"Temp/{name}", safe="/")
    url = mailbox_url(mailbox_upn, f"/drive/root:/{encoded}:/content")
    _, raw, _ = graph_bytes("PUT", url, access_token, body=data)
    return json.loads(raw.decode("utf-8"))


def delete_temp_item(mailbox_upn: str, item_id: str, access_token: str) -> None:
    if not item_id:
        return
    try:
        graph_bytes(
            "DELETE",
            mailbox_url(mailbox_upn, f"/drive/items/{urllib.parse.quote(item_id, safe='')}"),
            access_token,
            expected=(200, 202, 204, 404),
        )
    except Exception:
        pass


def convert_temp_item_to_pdf(mailbox_upn: str, item_id: str, access_token: str) -> bytes:
    url = mailbox_url(mailbox_upn, f"/drive/items/{urllib.parse.quote(item_id, safe='')}/content?format=pdf")
    _, raw, _ = graph_bytes("GET", url, access_token, timeout=180)
    if not raw:
        raise RuntimeError("Graph returned an empty PDF payload.")
    return raw


def graph_convert_bytes_to_pdf(mailbox_upn: str, access_token: str, suffix: str, data: bytes) -> bytes:
    item = upload_temp_bytes(mailbox_upn, access_token, suffix, data)
    item_id = str(item.get("id", "")).strip()
    try:
        return convert_temp_item_to_pdf(mailbox_upn, item_id, access_token)
    finally:
        delete_temp_item(mailbox_upn, item_id, access_token)


def recipient_label(value: dict[str, Any]) -> str:
    email_obj = (value or {}).get("emailAddress") or {}
    name = str(email_obj.get("name", "") or "").strip()
    address = str(email_obj.get("address", "") or "").strip()
    if name and address:
        return f"{name} <{address}>"
    return name or address


def recipient_list(values: Sequence[dict[str, Any]]) -> str:
    return "; ".join(label for label in (recipient_label(item) for item in values or []) if label)


def format_message_dt(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        stamp = dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return raw
    return stamp.astimezone().strftime("%d/%m/%Y %H:%M")


def safe_text(value: str) -> str:
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", str(value or "")).strip()


def visible_metadata_rows(message: dict[str, Any]) -> list[tuple[str, str]]:
    rows = [
        ("From", recipient_label(message.get("from") or message.get("sender") or {})),
        ("Sent", format_message_dt(str(message.get("sentDateTime") or message.get("receivedDateTime") or ""))),
        ("To", recipient_list(message.get("toRecipients") or [])),
        ("Cc", recipient_list(message.get("ccRecipients") or [])),
        ("Subject", str(message.get("subject", "") or "")),
    ]
    return [(label, safe_text(value)) for label, value in rows if value or label != "Cc"]


def fetch_inline_attachments(client: GraphClient, message_id: str) -> list[dict[str, str]]:
    quoted = urllib.parse.quote(message_id, safe="")
    payload = client.graph("GET", client.mailbox_path(f"/messages/{quoted}/attachments"))
    attachments: list[dict[str, str]] = []
    for row in payload.get("value", []) or []:
        if not isinstance(row, dict) or not bool(row.get("isInline")):
            continue
        attachment_id = str(row.get("id") or "").strip()
        if not attachment_id:
            continue
        detail = client.graph(
            "GET",
            client.mailbox_path(f"/messages/{quoted}/attachments/{urllib.parse.quote(attachment_id, safe='')}"),
        )
        if "fileAttachment" not in str(detail.get("@odata.type") or ""):
            continue
        content_id = str(detail.get("contentId") or "").strip().strip("<>")
        content_bytes = str(detail.get("contentBytes") or "").strip()
        if not content_id or not content_bytes:
            continue
        attachments.append(
            {
                "content_id": content_id,
                "content_type": str(detail.get("contentType") or "application/octet-stream").strip(),
                "content_bytes": content_bytes,
            }
        )
    return attachments


def embed_inline_images(body_html: str, inline_attachments: Sequence[dict[str, str]]) -> str:
    replacements: dict[str, str] = {}
    for attachment in inline_attachments:
        content_id = str(attachment.get("content_id") or "").strip().strip("<>").lower()
        content_bytes = str(attachment.get("content_bytes") or "").strip()
        if not content_id or not content_bytes:
            continue
        content_type = str(attachment.get("content_type") or "application/octet-stream").strip()
        replacements[content_id] = f"data:{content_type};base64,{content_bytes}"
    if not replacements:
        return body_html

    def replace(match: re.Match[str]) -> str:
        prefix = match.group("prefix")
        cid = urllib.parse.unquote(match.group("cid")).strip().strip("<>").lower()
        suffix = match.group("suffix")
        return f"{prefix}{replacements.get(cid, match.group('src'))}{suffix}"

    return re.sub(
        r"(?P<prefix>\bsrc\s*=\s*[\"'])(?P<src>cid:(?P<cid>[^\"'>\s]+))(?P<suffix>[\"'])",
        replace,
        body_html,
        flags=re.IGNORECASE,
    )


_ALLOWED_TAGS = {
    "p", "br", "div", "span", "b", "strong", "i", "em", "u", "ul", "ol", "li", "blockquote", "table", "thead",
    "tbody", "tfoot", "tr", "td", "th", "h1", "h2", "h3", "h4", "h5", "h6", "pre", "hr", "code", "sub", "sup",
}
_VOID_TAGS = {"br", "hr"}
_DROP_CONTENT_TAGS = {
    "script", "style", "iframe", "object", "frameset", "noscript", "template", "svg", "math",
    "head", "title", "form", "select", "textarea", "button", "applet", "audio", "video", "canvas",
}
_NUMERIC_ATTRS = {"td": {"colspan", "rowspan"}, "th": {"colspan", "rowspan"}}
_LINK_SCHEMES = ("http://", "https://", "mailto:")
_SELF_CONTAINED_IMAGE = re.compile(r"^data:image/(?:png|jpe?g|gif|bmp|webp);base64,[A-Za-z0-9+/=\s]+$", re.IGNORECASE)
BLOCKED_IMAGE_NOTE = "[image not loaded]"


class _EmailSanitiser(HTMLParser):

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.out: list[str] = []
        self._skip = 0
        self._open: list[str] = []
        self._href: list[str | None] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip:
            if tag in _DROP_CONTENT_TAGS:
                self._skip += 1
            return
        if tag in _DROP_CONTENT_TAGS:
            self._skip = 1
        elif tag == "img":
            values = {name: (value or "").strip() for name, value in attrs}
            src = values.get("src", "")
            if _SELF_CONTAINED_IMAGE.match(src):
                sizes = "".join(f' {key}="{values[key]}"' for key in ("width", "height") if values.get(key, "").isdigit())
                self.out.append(f'<img src="{src}"{sizes}>')
            else:
                self.out.append(f"<i>{BLOCKED_IMAGE_NOTE}</i>")
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            self._href.append(href.strip() if href.strip().lower().startswith(_LINK_SCHEMES) else None)
        elif tag in _ALLOWED_TAGS:
            kept = "".join(
                f' {name}="{value.strip()}"'
                for name, value in attrs
                if name in _NUMERIC_ATTRS.get(tag, ()) and (value or "").strip().isdigit()
            )
            self.out.append(f"<{tag}{kept}>")
            if tag not in _VOID_TAGS:
                self._open.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DROP_CONTENT_TAGS and not self._skip:
            return
        if tag == "a":
            return
        self.handle_starttag(tag, attrs)
        if tag in _ALLOWED_TAGS and tag not in _VOID_TAGS and not self._skip and self._open and self._open[-1] == tag:
            self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        if self._skip:
            if tag in _DROP_CONTENT_TAGS:
                self._skip -= 1
            return
        if tag == "a":
            if self._href:
                href = self._href.pop()
                if href:
                    self.out.append(f" ({html.escape(href, quote=True)})")
        elif tag in self._open:
            while self._open:
                top = self._open.pop()
                self.out.append(f"</{top}>")
                if top == tag:
                    break

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.out.append(html.escape(data, quote=True))

    def close(self) -> None:
        super().close()
        while self._open:
            self.out.append(f"</{self._open.pop()}>")


def sanitise_email_html(markup: str) -> str:
    parser = _EmailSanitiser()
    parser.feed(markup)
    parser.close()
    return "".join(parser.out)


def metadata_table_html(message: dict[str, Any]) -> str:
    rows = "\n".join(
        "<tr><th>{}</th><td>{}</td></tr>".format(html.escape(label), html.escape(value))
        for label, value in visible_metadata_rows(message)
    )
    return f'<table class="caseforge-email-meta">{rows}</table>' if rows else ""


def build_email_html(message: dict[str, Any], inline_attachments: Sequence[dict[str, str]], *, include_header: bool) -> bytes:
    body_obj = message.get("body") if isinstance(message.get("body"), dict) else {}
    body_html = str(body_obj.get("content") or "")
    if not re.search(r"<[a-z][^>]*>", body_html, flags=re.IGNORECASE):
        body_html = html.escape(body_html).replace("\r\n", "\n").replace("\r", "\n").replace("\n", "<br>\n")
    body_html = embed_inline_images(body_html, inline_attachments)
    body_html = sanitise_email_html(body_html)
    header_html = metadata_table_html(message) if include_header else ""
    page = f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <style>
    @page {{ size: A4 portrait; margin: 12mm; }}
    body {{
      color: #111;
      font-family: Calibri, Arial, sans-serif;
      font-size: 11pt;
      line-height: 1.35;
      margin: 0;
    }}
    .caseforge-email-meta {{
      border-collapse: collapse;
      table-layout: fixed;
      width: 100%;
      margin: 0 0 12px 0;
      page-break-inside: avoid;
    }}
    .caseforge-email-meta th,
    .caseforge-email-meta td {{
      border: 1px solid #b7b7b7;
      padding: 4px 6px;
      text-align: left;
      vertical-align: top;
    }}
    .caseforge-email-meta th {{
      background: #e9e9e9;
      font-weight: 700;
      white-space: nowrap;
      width: 72px;
    }}
    .caseforge-email-body img {{
      max-width: 100%;
      height: auto;
    }}
  </style>
</head>
<body>
  {header_html}
  <main class="caseforge-email-body">{body_html}</main>
</body>
</html>"""
    return page.encode("utf-8")


def write_metadata(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    args = parse_args()
    if not args.skip_permission_check:
        ensure_email_print_allowed(args.matter_id)

    client = GraphClient(
        tenant_id=_must(args.tenant_id, "GRAPH_TENANT_ID / --tenant-id"),
        client_id=_must(args.client_id, "GRAPH_MAIL_CLIENT_ID or GRAPH_CLIENT_ID / --client-id"),
        client_secret=_must(args.client_secret, "GRAPH_MAIL_CLIENT_SECRET or GRAPH_CLIENT_SECRET / --client-secret"),
        mailbox_upn=_must(args.mailbox_upn, "GRAPH_MAILBOX_UPN / --mailbox-upn"),
        max_retries=max(0, int(args.max_retries)),
        retry_base_seconds=max(0.1, float(args.retry_base_seconds)),
    )
    mail_token = client.token()
    files_token = graph_files.token()
    message = fetch_message_metadata(client, args.message_id)
    rendering = "graph-server-side-html"
    inline_attachments = fetch_inline_attachments(client, args.message_id)
    html_bytes = build_email_html(message, inline_attachments, include_header=not bool(args.no_cover))
    try:
        final_pdf = graph_convert_bytes_to_pdf(args.mailbox_upn, files_token, ".html", html_bytes)
    except Exception:
        mime_bytes = fetch_message_mime(args.mailbox_upn, args.message_id, mail_token)
        final_pdf = graph_convert_bytes_to_pdf(args.mailbox_upn, files_token, ".eml", mime_bytes)
        rendering = "graph-server-side-eml-fallback"

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(final_pdf)
    metadata = {
        "message_id": args.message_id,
        "internet_message_id": str(message.get("internetMessageId", "") or ""),
        "subject": str(message.get("subject", "") or ""),
        "output": str(output),
        "bytes": output.stat().st_size,
        "cover_page": False,
        "metadata_header": not bool(args.no_cover),
        "inline_attachments_embedded": len(inline_attachments),
        "rendering": rendering,
    }
    if args.metadata_json:
        write_metadata(Path(args.metadata_json), metadata)
    try:
        from telemetry_sqlite import record_runtime_event, utc_now_z

        record_runtime_event(
            {
                "timestamp": utc_now_z(),
                "event_name": "print_email_to_pdf",
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", ""),
                "model_label": os.getenv("CASEFORGE_MODEL_LABEL", ""),
                "command": "python tools/documents/print_email_to_pdf.py",
                "files_read": ["tools/documents/print_email_to_pdf.py"],
                "files_written": [str(output), *([args.metadata_json] if args.metadata_json else [])],
                "metrics": metadata,
            }
        )
    except Exception:
        pass
    print(json.dumps(metadata, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
