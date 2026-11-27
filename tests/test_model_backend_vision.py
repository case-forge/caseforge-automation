from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import model_backend as mb


def _capture(monkeypatch):
    seen = {}

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({
                "choices": [{"message": {"content": "TRANSCRIBED"}}],
                "usage": {"prompt_tokens": 1764, "completion_tokens": 75},
            }).encode()

    def fake_urlopen(req, timeout=None):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data.decode())
        seen["headers"] = dict(req.headers)
        return _Resp()

    monkeypatch.setattr(mb.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENROUTER_OCR_API_KEY", "k")
    return seen


def test_vision_call_enforces_zdr_and_denies_data_collection(monkeypatch):
    seen = _capture(monkeypatch)
    mb.run_vision(b"\x89PNG-fake", "Transcribe this")
    prov = seen["body"]["provider"]
    assert prov["zdr"] is True
    assert prov["data_collection"] == "deny"


def test_vision_call_sends_the_image_and_pins_the_model(monkeypatch):
    seen = _capture(monkeypatch)
    mb.run_vision(b"\x89PNG-fake", "Transcribe this")
    content = seen["body"]["messages"][0]["content"]
    kinds = [part["type"] for part in content]
    assert "image_url" in kinds and "text" in kinds
    assert seen["body"]["model"] == mb.vision_model()
    assert "auto" not in seen["body"]["model"]


def test_vision_returns_the_transcription_and_usage(monkeypatch):
    seen = _capture(monkeypatch)
    usage = {}
    out = mb.run_vision(b"\x89PNG-fake", "Transcribe this", usage=usage)
    assert out == "TRANSCRIBED"
    assert usage.get("completion_tokens") == 75


def test_vision_without_a_key_fails_loudly(monkeypatch):
    monkeypatch.delenv("OPENROUTER_OCR_API_KEY", raising=False)
    with pytest.raises(mb.ModelBackendError):
        mb.run_vision(b"\x89PNG-fake", "Transcribe this")


def test_vision_never_falls_back_to_the_shared_key(monkeypatch):
    calls = []
    monkeypatch.setattr(mb.urllib.request, "urlopen", lambda *a, **k: calls.append(a))
    monkeypatch.setenv("OPENROUTER_API_KEY", "shared")
    monkeypatch.delenv("OPENROUTER_OCR_API_KEY", raising=False)
    with pytest.raises(mb.ModelBackendError, match="OPENROUTER_OCR_API_KEY"):
        mb.run_vision(b"\x89PNG-fake", "Transcribe this")
    assert calls == []


def test_vision_sends_the_ocr_key_not_the_shared_one(monkeypatch):
    seen = _capture(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "shared")
    monkeypatch.setenv("OPENROUTER_OCR_API_KEY", "ocr-only")
    mb.run_vision(b"\x89PNG-fake", "Transcribe this")
    assert seen["headers"]["Authorization"] == "Bearer ocr-only"



def test_sniff_image_mime_detects_real_formats():
    assert mb._sniff_image_mime(b"\xff\xd8\xff\xe0rest") == "image/jpeg"
    assert mb._sniff_image_mime(b"\x89PNG\r\n\x1a\nrest") == "image/png"
    assert mb._sniff_image_mime(b"GIF89arest") == "image/gif"
    assert mb._sniff_image_mime(b"RIFF\x00\x00\x00\x00WEBPrest") == "image/webp"
    assert mb._sniff_image_mime(b"not a real image") == "image/png"


def test_vision_call_declares_the_real_mime_type_for_a_jpeg(monkeypatch):
    seen = _capture(monkeypatch)
    mb.run_vision(b"\xff\xd8\xff\xe0real-jpeg-bytes", "Transcribe this")
    content = seen["body"]["messages"][0]["content"]
    image_part = next(part for part in content if part["type"] == "image_url")
    assert image_part["image_url"]["url"].startswith("data:image/jpeg;base64,")


def _capture_error(monkeypatch, error_payload):
    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return json.dumps({"error": error_payload}).encode()

    def fake_urlopen(req, timeout=None):
        return _Resp()

    monkeypatch.setattr(mb.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("OPENROUTER_OCR_API_KEY", "k")


def test_vision_raises_a_clear_error_instead_of_a_raw_keyerror_on_provider_refusal(monkeypatch):
    _capture_error(monkeypatch, {"message": "MIME type mismatch", "code": 400})
    with pytest.raises(mb.ModelBackendError, match="MIME type mismatch"):
        mb.run_vision(b"\xff\xd8\xff\xe0real-jpeg-bytes", "Transcribe this")



def _varied_prose(target_chars: int) -> str:
    import random

    rng = random.Random(42)
    vocab = (
        "applicant respondent order court hearing molestation prohibited steps "
        "district judge sitting private notice proceedings undertaking family "
        "children act section served personally solicitor counsel bundle date "
        "return listed dismissed granted paragraph schedule allegations contact"
    ).split()
    out: list[str] = []
    while sum(len(w) + 1 for w in out) < target_chars:
        out.append(rng.choice(vocab))
    return " ".join(out)


def test_vision_max_tokens_scales_with_page_count():
    assert mb.vision_max_tokens_for_pages(5) == 7500
    assert mb.vision_max_tokens_for_pages(1) == 2000
    assert mb.vision_max_tokens_for_pages(23) == 16000
    assert mb.vision_max_tokens_for_pages(200) == 16000
    assert mb.vision_max_tokens_for_pages(5) < 65535


def test_vision_calls_send_a_max_tokens_ceiling(monkeypatch):
    seen = _capture(monkeypatch)
    mb.run_vision(b"\x89PNG-fake", "Transcribe this")
    assert seen["body"]["max_tokens"] == mb.DEFAULT_VISION_MAX_TOKENS


def test_explicit_max_tokens_overrides_the_default(monkeypatch):
    seen = _capture(monkeypatch)
    mb.run_vision(b"\x89PNG-fake", "Transcribe this", max_tokens=7500)
    assert seen["body"]["max_tokens"] == 7500


def test_real_prose_is_not_flagged_as_degenerate():
    for chars, pages in ((4000, 1), (8748, 4), (30000, 23)):
        degenerate, why = mb.looks_degenerate(_varied_prose(chars), pages=pages)
        assert degenerate is False, f"real prose flagged at {chars} chars: {why}"
    assert mb.looks_degenerate("", pages=1) == (False, "")


def test_repetition_loop_is_caught_by_volume_per_page():
    loop = "The respondent gave undertakings to the court. " * 5700
    degenerate, why = mb.looks_degenerate(loop, pages=5)
    assert degenerate is True
    assert "chars/page" in why


def test_repetition_loop_is_caught_even_when_spread_over_many_pages():
    loop = "The respondent gave undertakings to the court. " * 5700
    degenerate, why = mb.looks_degenerate(loop, pages=60)
    assert degenerate is True
    assert "repetition" in why
