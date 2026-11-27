#!/usr/bin/env python3

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import secrets
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import monitoring.telegram_text_safety as telegram_text_safety

STATE_DIR = REPO_ROOT / "telemetry" / "counsel-bot"
POOL_PATH = STATE_DIR / "pool.json"
OFFERS_DIR = STATE_DIR / "offers"
LOG_PATH = STATE_DIR / "counsel-bot.log"
_API = "https://api.telegram.org/bot{token}/{method}"

ACCEPT_CB = "acc"
DECLINE_CB = "dec"


def bot_token() -> str:
    return (os.environ.get("CASEFORGE_COUNSEL_TELEGRAM_BOT_TOKEN") or "").strip()


def owner_chat_id() -> str:
    return (
        os.environ.get("CASEFORGE_COUNSEL_OWNER_CHAT_ID")
        or os.environ.get("CASEFORGE_MONITOR_TELEGRAM_CHAT_ID")
        or ""
    ).strip()


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _log(record: dict) -> None:
    try:
        LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        record["ts"] = _now()
        with LOG_PATH.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def load_pool(*, state_dir: Path = STATE_DIR) -> dict[str, dict]:
    path = state_dir / "pool.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def _clean_firm(firm: str) -> str:
    collapsed = " ".join((firm or "").split())
    printable = "".join(ch for ch in collapsed if ch.isprintable())
    return (printable or "Counsel")[:80]


def register_counsel(chat_id: Any, firm: str, *, state_dir: Path = STATE_DIR) -> bool:
    pool = load_pool(state_dir=state_dir)
    key = str(chat_id)
    is_new = key not in pool
    val = _clean_firm(firm)
    pool[key] = {
        "firm": val,
        "name": val,
        "joined_at": pool.get(key, {}).get("joined_at") or _now(),
    }
    path = state_dir / "pool.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pool, indent=2), encoding="utf-8")
    return is_new


def load_allowed(*, state_dir: Path = STATE_DIR) -> set[str]:
    try:
        rows = json.loads((state_dir / "allowed.json").read_text(encoding="utf-8"))
    except Exception:
        rows = []
    allowed = {str(r) for r in rows} if isinstance(rows, list) else set()
    owner = owner_chat_id()
    if owner:
        allowed.add(owner)
    return allowed


def approve_counsel(chat_id: Any, *, state_dir: Path = STATE_DIR) -> None:
    allowed = sorted(load_allowed(state_dir=state_dir) | {str(chat_id)})
    path = state_dir / "allowed.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(allowed, indent=2), encoding="utf-8")


def load_pending(*, state_dir: Path = STATE_DIR) -> dict[str, dict]:
    try:
        return json.loads((state_dir / "pending.json").read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def request_registration(chat_id: Any, firm: str, *, state_dir: Path = STATE_DIR) -> bool:
    pending = load_pending(state_dir=state_dir)
    key = str(chat_id)
    is_new = key not in pending
    pending[key] = {"firm": _clean_firm(firm), "asked_at": pending.get(key, {}).get("asked_at") or _now()}
    path = state_dir / "pending.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(pending, indent=2), encoding="utf-8")
    return is_new


def firm_for(chat_id: Any, frm: dict, *, state_dir: Path = STATE_DIR) -> str:
    entry = load_pool(state_dir=state_dir).get(str(chat_id)) or {}
    return _clean_firm(entry.get("firm") or _display_name(frm or {}))


def make_offer_id() -> str:
    return secrets.token_hex(4)


def _offer_path(offer_id: str, state_dir: Path) -> Path:
    return state_dir / "offers" / f"{offer_id}.json"


def load_offer(offer_id: str, *, state_dir: Path = STATE_DIR) -> Optional[dict]:
    try:
        return json.loads(_offer_path(offer_id, state_dir).read_text(encoding="utf-8"))
    except Exception:
        return None


def save_offer(offer: dict, *, state_dir: Path = STATE_DIR) -> None:
    path = _offer_path(offer["offer_id"], state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(offer, indent=2), encoding="utf-8")


def _norm_funding(value: str) -> str:
    v = (value or "").strip().lower()
    if v in {"la", "legal aid", "legal-aid", "legalaid", "aid", "public"}:
        return "Legal aid"
    if v in {"private", "privately funded", "priv", "payer", "private payer"}:
        return "Private payer"
    return (value or "Unspecified").strip()


def build_offer(
    *,
    court: str,
    date: str,
    time_: str,
    matter: str,
    funding: str,
    hearing: str = "",
    time_estimate: str = "",
    offer_id: Optional[str] = None,
) -> dict:
    return {
        "offer_id": offer_id or make_offer_id(),
        "court": court.strip(),
        "date": date.strip(),
        "time": time_.strip(),
        "matter": matter.strip(),
        "hearing": (hearing or "").strip(),
        "time_estimate": (time_estimate or "").strip(),
        "funding": _norm_funding(funding),
        "created_at": _now(),
        "status": "open",
        "winner": None,
        "messages": {},
    }


def format_offer_card(offer: dict) -> str:
    head = f"⚖️ {offer.get('matter') or '—'}"
    if offer.get("hearing"):
        head += f": {offer['hearing']}"
    date_line = f"📅 Date: {offer.get('date') or '—'}"
    if offer.get("time"):
        date_line += f" at {offer['time']}"
    return "\n".join(
        [
            head,
            f"🏛 Court: {offer.get('court') or '—'}",
            date_line,
            f"🕙 Time Estimate: {offer.get('time_estimate') or '—'}",
            f"💷 Funding: {offer.get('funding') or '—'}",
        ]
    )


def taken_card(offer: dict, *, mine: bool = False) -> str:
    matter = offer.get("matter") or "this brief"
    head = f"🎉 {matter} is yours!" if mine else f"🔒 {matter} — this brief has been taken."
    date_line = f"📅 {offer.get('date') or '—'}"
    if offer.get("time"):
        date_line += f" at {offer['time']}"
    return "\n".join(
        [
            head,
            "",
            f"🏛 {offer.get('court') or '—'}   {date_line}",
            f"🕙 Time Estimate: {offer.get('time_estimate') or '—'}   💷 {offer.get('funding') or '—'}",
        ]
    )


def offer_keyboard(offer_id: str) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "✅ Accept", "callback_data": f"{ACCEPT_CB}:{offer_id}"},
                {"text": "❌ Decline", "callback_data": f"{DECLINE_CB}:{offer_id}"},
            ]
        ]
    }


def parse_callback(data: str) -> tuple[str, str]:
    s = (data or "").strip()
    if ":" not in s:
        return "", ""
    action, _, offer_id = s.partition(":")
    if action not in {ACCEPT_CB, DECLINE_CB}:
        return "", ""
    return action, offer_id.strip()


def claim_offer(
    offer_id: str, chat_id: Any, firm: str, *, state_dir: Path = STATE_DIR
) -> dict:
    offer = load_offer(offer_id, state_dir=state_dir)
    if offer is None:
        return {"result": "unknown", "offer": None}
    if str(chat_id) not in load_pool(state_dir=state_dir):
        return {"result": "not_registered", "offer": offer}

    lock = _offer_path(offer_id, state_dir).with_suffix(".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return {"result": "already_taken", "offer": load_offer(offer_id, state_dir=state_dir)}

    try:
        os.write(fd, str(chat_id).encode("utf-8"))
    finally:
        os.close(fd)
    offer["status"] = "taken"
    offer["winner"] = {"chat_id": str(chat_id), "firm": _clean_firm(firm), "at": _now()}
    save_offer(offer, state_dir=state_dir)
    return {"result": "won", "offer": offer}


def _api_call(token: str, method: str, params: dict, *, timeout: int = 10) -> dict:
    url = _API.format(token=token, method=method)
    data = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _guarded(text: str) -> bool:
    if telegram_text_safety.looks_unsafe(text):
        _log({"event": "blocked_pii_outbound", "len": len(text)})
        return False
    return True


def send_card(token: str, chat_id: Any, offer: dict, *, timeout: int = 10) -> Optional[int]:
    text = format_offer_card(offer)
    if not _guarded(text):
        return None
    try:
        body = _api_call(
            token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text,
                "reply_markup": json.dumps(offer_keyboard(offer["offer_id"])),
                "disable_web_page_preview": "true",
            },
            timeout=timeout,
        )
        if body.get("ok"):
            return int(body["result"]["message_id"])
    except Exception as exc:
        _log({"event": "send_card_error", "error": telegram_text_safety.redact_token(str(exc), token)[:200]})
    return None


def send_text(token: str, chat_id: Any, text: str, *, timeout: int = 10) -> bool:
    if not _guarded(text):
        return False
    try:
        body = _api_call(
            token,
            "sendMessage",
            {"chat_id": chat_id, "text": text, "disable_web_page_preview": "true"},
            timeout=timeout,
        )
        return bool(body.get("ok"))
    except Exception as exc:
        _log({"event": "send_text_error", "error": telegram_text_safety.redact_token(str(exc), token)[:200]})
        return False


def edit_card(token: str, chat_id: Any, message_id: int, text: str, *, timeout: int = 10) -> bool:
    if not _guarded(text):
        return False
    try:
        body = _api_call(
            token,
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": json.dumps({"inline_keyboard": []}),
            },
            timeout=timeout,
        )
        return bool(body.get("ok"))
    except Exception as exc:
        _log({"event": "edit_card_error", "error": telegram_text_safety.redact_token(str(exc), token)[:200]})
        return False


def answer_callback(token: str, callback_id: str, text: str = "", *, timeout: int = 10) -> bool:
    try:
        body = _api_call(
            token,
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": text, "show_alert": "false"},
            timeout=timeout,
        )
        return bool(body.get("ok"))
    except Exception as exc:
        _log({"event": "answer_cb_error", "error": telegram_text_safety.redact_token(str(exc), token)[:200]})
        return False


def get_updates(token: str, *, offset: int = 0, timeout: int = 30) -> list[dict]:
    try:
        body = _api_call(
            token,
            "getUpdates",
            {"offset": offset, "timeout": timeout, "allowed_updates": json.dumps(["message", "callback_query"])},
            timeout=timeout + 10,
        )
    except Exception as exc:
        _log({"event": "get_updates_error", "error": telegram_text_safety.redact_token(str(exc), token)[:200]})
        return []
    return body.get("result", []) if body.get("ok") else []


def broadcast_offer(
    offer: dict,
    *,
    token: Optional[str] = None,
    state_dir: Path = STATE_DIR,
    sender: Callable[..., Optional[int]] = send_card,
) -> dict:
    token = token or bot_token()
    pool = load_pool(state_dir=state_dir)
    if not token:
        _log({"event": "broadcast_no_token", "offer_id": offer.get("offer_id")})
        return {"sent": 0, "pool": len(pool), "offer_id": offer.get("offer_id")}
    sent = 0
    for chat_id in pool:
        message_id = sender(token, chat_id, offer)
        if message_id is not None:
            offer["messages"][str(chat_id)] = message_id
            sent += 1
    save_offer(offer, state_dir=state_dir)
    _log({"event": "broadcast", "offer_id": offer["offer_id"], "sent": sent, "pool": len(pool)})
    _emit_telemetry("counsel-offer-broadcast", recipients=sent, pool=len(pool))
    return {"sent": sent, "pool": len(pool), "offer_id": offer["offer_id"]}


def _command(text: str) -> str:
    token = (text or "").strip().split(maxsplit=1)[0] if (text or "").strip() else ""
    return token.split("@", 1)[0].lower()


def _display_name(frm: dict) -> str:
    parts = [frm.get("first_name"), frm.get("last_name")]
    name = " ".join(p for p in parts if p).strip()
    if not name and frm.get("username"):
        name = "@" + frm["username"]
    return name or "Counsel"


def handle_message(
    update: dict,
    *,
    register: Callable[[Any, str], bool] = register_counsel,
    is_allowed: Optional[Callable[[Any], bool]] = None,
    request: Optional[Callable[[Any, str], Any]] = None,
) -> Optional[tuple[Any, str]]:
    if is_allowed is None:
        is_allowed = lambda cid: str(cid) in load_allowed()
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = chat.get("id")
    text = message.get("text") or ""
    if chat_id is None or not text:
        return None
    cmd = _command(text)
    if cmd in {"/start", "/join"}:
        rest = text.strip().split(maxsplit=1)
        firm = rest[1].strip() if len(rest) > 1 else _display_name(message.get("from") or {})
        if not is_allowed(chat_id):
            if request is not None:
                request(chat_id, firm)
            return chat_id, "Thanks. Your request has gone to CaseForge for approval; you will be told once you are on the list."
        is_new = register(chat_id, firm)
        if is_new:
            return chat_id, (
                f"You're registered for CaseForge counsel briefs as {firm}. ✅\n"
                "When a brief comes up you'll get a card here — tap ✅ to accept. "
                "Fastest finger wins, so be quick.\n"
                "To change the firm name shown when you accept, send /start <firm name>."
            )
        return chat_id, f"You're already on the list for CaseForge counsel briefs as {firm}. ✅"
    if cmd == "/help":
        return chat_id, (
            "CaseForge counsel briefs bot.\n"
            "/start <firm name> — get briefs offered to you here (name is shown when you accept)\n"
            "When a brief arrives, tap ✅ to accept (fastest finger wins) or ❌ to pass."
        )
    return chat_id, "Send /start to receive counsel briefs here, or /help."


def _notify_registration_request(token: str, chat_id: Any, firm: str, *, state_dir: Path = STATE_DIR) -> None:
    if not request_registration(chat_id, firm, state_dir=state_dir):
        return
    owner = owner_chat_id()
    if owner:
        send_text(token, owner, f"Counsel bot: chat {chat_id} asks to join as '{_clean_firm(firm)}'. Approve: counsel_bot.py approve {chat_id}")


def process_updates(
    token: str,
    updates: list[dict],
    *,
    state_dir: Path = STATE_DIR,
) -> int:
    next_offset = 0
    for update in updates:
        next_offset = max(next_offset, int(update.get("update_id", 0)) + 1)
        if "callback_query" in update:
            _handle_callback(token, update["callback_query"], state_dir=state_dir)
            continue
        result = handle_message(
            update,
            is_allowed=lambda cid: str(cid) in load_allowed(state_dir=state_dir),
            request=lambda cid, firm: _notify_registration_request(token, cid, firm, state_dir=state_dir),
        )
        if result is not None:
            chat_id, reply = result
            send_text(token, chat_id, reply)
    return next_offset


def _handle_callback(token: str, cb: dict, *, state_dir: Path = STATE_DIR) -> None:
    cb_id = cb.get("id", "")
    data = cb.get("data") or ""
    frm = cb.get("from") or {}
    msg = cb.get("message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    message_id = msg.get("message_id")
    firm = firm_for(chat_id, frm, state_dir=state_dir)

    action, offer_id = parse_callback(data)
    if not action:
        answer_callback(token, cb_id, "")
        return

    if action == DECLINE_CB:
        answer_callback(token, cb_id, "No problem — passed.")
        if chat_id is not None and message_id is not None:
            offer = load_offer(offer_id, state_dir=state_dir) or {"matter": "", "court": "", "date": "", "time": "", "funding": ""}
            edit_card(token, chat_id, message_id, f"❌ You passed on {offer.get('matter') or 'this brief'}.")
        return

    outcome = claim_offer(offer_id, chat_id, firm, state_dir=state_dir)
    result = outcome["result"]
    offer = outcome.get("offer")

    if result == "unknown":
        answer_callback(token, cb_id, "Sorry — this brief is no longer available.")
        return

    if result == "not_registered":
        answer_callback(token, cb_id, "You are not on the list for these briefs.")
        return

    if result == "won":
        answer_callback(token, cb_id, "🎉 It's yours! Congratulations.")
        if chat_id is not None and message_id is not None:
            edit_card(token, chat_id, message_id, taken_card(offer, mine=True))
        when = f"{offer.get('date')} at {offer.get('time')}" if offer.get("time") else offer.get("date")
        send_text(
            token,
            chat_id,
            f"🎉 Congratulations {firm} — {offer.get('matter')} is yours.\n"
            f"🏛 {offer.get('court')}  📅 {when}.\n"
            "CaseForge will be in touch with the papers.",
        )
        for other_chat, other_msg in (offer.get("messages") or {}).items():
            if str(other_chat) == str(chat_id):
                continue
            edit_card(token, other_chat, other_msg, taken_card(offer, mine=False))
        owner = owner_chat_id()
        if owner:
            send_text(
                token,
                owner,
                f"✅ Brief {offer.get('matter')} accepted by {firm} ({offer.get('funding')}) [chat {chat_id}].",
            )
        _log({"event": "offer_won", "offer_id": offer_id})
        _emit_telemetry("counsel-offer-accepted")
        return

    answer_callback(token, cb_id, "Too slow — this brief has already been taken.")
    if chat_id is not None and message_id is not None and offer is not None:
        edit_card(token, chat_id, message_id, taken_card(offer, mine=False))


def poll_loop(*, poll_timeout: int = 30, state_dir: Path = STATE_DIR) -> int:
    token = bot_token()
    if not token:
        print("CASEFORGE_COUNSEL_TELEGRAM_BOT_TOKEN not set; nothing to poll.", file=sys.stderr)
        return 2
    _log({"event": "start", "owner_set": bool(owner_chat_id())})
    _emit_telemetry("counsel-bot-start")
    offset = 0
    while True:
        updates = get_updates(token, offset=offset, timeout=poll_timeout)
        if updates:
            offset = process_updates(token, updates, state_dir=state_dir)
        else:
            time.sleep(1)


def _emit_telemetry(event: str, **metrics: Any) -> None:
    try:
        from telemetry_sqlite import record_runtime_event

        record_runtime_event(
            {
                "timestamp": _now(),
                "event_name": event,
                "runtime_label": os.getenv("CASEFORGE_RUNTIME_LABEL", "counsel-bot"),
                "command": "products/ikoro/counsel_bot.py",
                "files_read": [],
                "files_written": [],
                "metrics": metrics,
            }
        )
    except Exception:
        pass


def _bootstrap_val_env() -> None:
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from env_bootstrap import load_repo_secrets

        load_repo_secrets()
    except Exception:
        pass

def main(argv: list[str] | None = None) -> int:
    _bootstrap_val_env()
    ap = argparse.ArgumentParser(description="CaseForge Counsel fastest-fingers-first brief bot")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_offer = sub.add_parser("offer", help="Broadcast a brief offer to the counsel pool.")
    p_offer.add_argument("--court", required=True)
    p_offer.add_argument("--date", required=True)
    p_offer.add_argument("--time", required=True)
    p_offer.add_argument("--matter", required=True, help="Matter REFERENCE only — never a client name.")
    p_offer.add_argument("--funding", required=True, help="e.g. 'legal aid' or 'private'.")
    p_offer.add_argument("--hearing", default="", help="Order/hearing types for the header, e.g. 'NMO/CAO/SIO & OO'.")
    p_offer.add_argument("--time-estimate", dest="time_estimate", default="", help="e.g. '1hr'.")

    p_poll = sub.add_parser("poll", help="Run the long-poll loop (registration + the race).")
    p_poll.add_argument("--poll-timeout", type=int, default=30)

    sub.add_parser("pool", help="List registered counsel (owner view).")
    sub.add_parser("pending", help="List chats waiting for owner approval.")
    p_approve = sub.add_parser("approve", help="Approve a chat id to register for briefs.")
    p_approve.add_argument("chat_id")

    args = ap.parse_args(argv)

    if args.cmd == "pool":
        pool = load_pool()
        if not pool:
            print("No counsel registered yet. Ask them to send /start to the bot.")
            return 0
        for chat_id, info in pool.items():
            print(f"{chat_id}\t{info.get('name')}\t(joined {info.get('joined_at')})")
        return 0

    if args.cmd == "pending":
        for chat_id, info in load_pending().items():
            print(f"{chat_id}\t{info.get('firm')}\t(asked {info.get('asked_at')})")
        return 0

    if args.cmd == "approve":
        approve_counsel(args.chat_id)
        print(f"approved: {args.chat_id}; they can now send /start")
        return 0

    if args.cmd == "offer":
        if not bot_token():
            print("CASEFORGE_COUNSEL_TELEGRAM_BOT_TOKEN not set.", file=sys.stderr)
            return 2
        offer = build_offer(
            court=args.court,
            date=args.date,
            time_=args.time,
            matter=args.matter,
            funding=args.funding,
            hearing=args.hearing,
            time_estimate=args.time_estimate,
        )
        result = broadcast_offer(offer)
        print(
            f"Offer {result['offer_id']} sent to {result['sent']}/{result['pool']} counsel. "
            "First to tap ✅ wins."
        )
        return 0 if result["sent"] else 1

    if args.cmd == "poll":
        return poll_loop(poll_timeout=args.poll_timeout)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
