import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
for p in (REPO_ROOT, REPO_ROOT / "tools", REPO_ROOT / "tools" / "monitoring"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

import products.ikoro.counsel_bot as bot


@pytest.fixture
def state_dir(tmp_path):
    return tmp_path / "counsel-bot"


@pytest.fixture(autouse=True)
def _isolate_log(monkeypatch, tmp_path):
    monkeypatch.setattr(bot, "LOG_PATH", tmp_path / "counsel-bot.log")


def _offer(state_dir, **overrides):
    o = bot.build_offer(
        court=overrides.get("court", "Central Family Court"),
        date=overrides.get("date", "Mon 30 Jun 2026"),
        time_=overrides.get("time", "10:00"),
        matter=overrides.get("matter", "CaseForge-2231"),
        funding=overrides.get("funding", "legal aid"),
        offer_id=overrides.get("offer_id", "abcd1234"),
    )
    bot.save_offer(o, state_dir=state_dir)
    return o


def test_card_carries_the_brief_facts_and_is_pii_safe():
    card = bot.format_offer_card(_card_offer())
    for needle in ("Central Family Court", "Mon 30 Jun 2026", "10:00", "CaseForge-2231", "Legal aid"):
        assert needle in card
    assert card.splitlines()[0] == "⚖️ CaseForge-2231: NMO/CAO/SIO & OO"
    assert "Date: Mon 30 Jun 2026 at 10:00" in card
    assert "Time Estimate: 1hr" in card
    import monitoring.telegram_text_safety as safety
    assert not safety.looks_unsafe(card)


def test_funding_is_normalised():
    assert bot.build_offer(court="c", date="d", time_="t", matter="m", funding="LA")["funding"] == "Legal aid"
    assert bot.build_offer(court="c", date="d", time_="t", matter="m", funding="private")["funding"] == "Private payer"


def _card_offer():
    return bot.build_offer(
        court="Central Family Court", date="Mon 30 Jun 2026", time_="10:00",
        matter="CaseForge-2231", funding="legal aid", hearing="NMO/CAO/SIO & OO",
        time_estimate="1hr", offer_id="abcd1234",
    )


def test_keyboard_and_callback_roundtrip():
    kb = bot.offer_keyboard("abcd1234")
    accept = kb["inline_keyboard"][0][0]["callback_data"]
    assert bot.parse_callback(accept) == ("acc", "abcd1234")
    assert bot.parse_callback("dec:abcd1234") == ("dec", "abcd1234")
    assert bot.parse_callback("garbage") == ("", "")
    assert len(accept.encode()) <= 64


def test_first_tap_wins_second_is_already_taken(state_dir):
    _offer(state_dir)
    bot.register_counsel(111, "Sam", state_dir=state_dir)
    bot.register_counsel(222, "Riley", state_dir=state_dir)
    first = bot.claim_offer("abcd1234", 111, "Sam", state_dir=state_dir)
    second = bot.claim_offer("abcd1234", 222, "Riley", state_dir=state_dir)
    assert first["result"] == "won"
    assert second["result"] == "already_taken"
    assert first["offer"]["winner"]["chat_id"] == "111"
    assert second["offer"]["winner"]["firm"] == "Sam"
    assert bot.load_offer("abcd1234", state_dir=state_dir)["status"] == "taken"
    loser_card = bot.taken_card(second["offer"], mine=False)
    assert "Sam" not in loser_card
    assert "taken" in loser_card.lower()


def test_claim_unknown_offer():
    assert bot.claim_offer("nope", 1, "x", state_dir=Path("/nonexistent"))["result"] == "unknown"


def test_register_counsel_is_idempotent(state_dir):
    assert bot.register_counsel(555, "Sam", state_dir=state_dir) is True
    assert bot.register_counsel(555, "Sam", state_dir=state_dir) is False
    pool = bot.load_pool(state_dir=state_dir)
    assert pool["555"]["firm"] == "Sam"


def test_firm_name_cannot_inject_card_lines(state_dir):
    bot.register_counsel(777, "Evil\n💷 Funding: Private payer\x00", state_dir=state_dir)
    stored = bot.load_pool(state_dir=state_dir)["777"]["firm"]
    assert "\n" not in stored and "\x00" not in stored
    assert stored == "Evil 💷 Funding: Private payer"
    _offer(state_dir, offer_id="dead0001")
    bot.register_counsel(777, "Evil", state_dir=state_dir)
    won = bot.claim_offer("dead0001", 777, "X\nY", state_dir=state_dir)
    assert "\n" not in won["offer"]["winner"]["firm"]


def test_start_registers_and_replies():
    seen = []
    update = {"update_id": 1, "message": {"text": "/start", "chat": {"id": 9}, "from": {"first_name": "Dora", "last_name": "KC"}}}
    result = bot.handle_message(update, register=lambda c, n: seen.append((c, n)) or True, is_allowed=lambda c: True)
    assert seen == [(9, "Dora KC")]
    chat_id, reply = result
    assert chat_id == 9
    assert "registered" in reply.lower()


def test_broadcast_records_message_ids(state_dir, monkeypatch):
    bot.register_counsel(111, "Alice", state_dir=state_dir)
    bot.register_counsel(222, "Bob", state_dir=state_dir)
    offer = bot.build_offer(court="c", date="d", time_="t", matter="CaseForge-9", funding="private", offer_id="ffff0000")
    sent_to = []

    def fake_sender(token, chat_id, off):
        sent_to.append(str(chat_id))
        return 1000 + int(chat_id)

    res = bot.broadcast_offer(offer, token="T", state_dir=state_dir, sender=fake_sender)
    assert res["sent"] == 2
    saved = bot.load_offer("ffff0000", state_dir=state_dir)
    assert saved["messages"]["111"] == 1111
    assert set(sent_to) == {"111", "222"}


def test_send_text_blocks_unsafe(monkeypatch):
    calls = []
    monkeypatch.setattr(bot, "_api_call", lambda *a, **k: calls.append(a) or {"ok": True})
    assert bot.send_text("T", 1, "email clerk at clerks@chambers.example") is False
    assert calls == []


def test_edit_card_explicitly_clears_the_inline_keyboard(monkeypatch):
    calls = []

    def fake_api_call(token, method, params, timeout=10):
        calls.append((method, params))
        return {"ok": True}

    monkeypatch.setattr(bot, "_api_call", fake_api_call)

    assert bot.edit_card("T", 1, 42, "Brief taken by Alice.") is True
    assert len(calls) == 1
    method, params = calls[0]
    assert method == "editMessageText"
    assert json.loads(params["reply_markup"]) == {"inline_keyboard": []}


def test_start_from_unapproved_chat_only_requests(state_dir):
    asked = []
    update = {"update_id": 1, "message": {"text": "/start Some Firm", "chat": {"id": 31}, "from": {"first_name": "X"}}}
    chat_id, reply = bot.handle_message(
        update,
        register=lambda c, n: (_ for _ in ()).throw(AssertionError("registered an unapproved chat")),
        is_allowed=lambda c: False,
        request=lambda c, n: asked.append((c, n)),
    )
    assert asked == [(31, "Some Firm")] and "approval" in reply.lower()


def test_owner_approval_allows_registration(state_dir):
    assert "31" not in bot.load_allowed(state_dir=state_dir)
    bot.approve_counsel(31, state_dir=state_dir)
    assert "31" in bot.load_allowed(state_dir=state_dir)
