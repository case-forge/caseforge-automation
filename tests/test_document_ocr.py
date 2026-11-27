from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import document_ocr as ocr


def _tsv(rows):
    header = "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
    lines = [header]
    for conf, text in rows:
        lines.append("5\t1\t1\t1\t1\t1\t0\t0\t10\t10\t%s\t%s" % (conf, text))
    return "\n".join(lines)


def test_parses_mean_confidence_and_text_from_tsv():
    out = ocr.parse_tesseract_tsv(_tsv([(95, "Sample"), (90, "Scanned"), (85, "Text")]))
    assert out.text == "Sample Scanned Text"
    assert 89 <= out.mean_conf <= 91
    assert out.word_count == 3


def test_a_confident_page_does_not_escalate():
    out = ocr.parse_tesseract_tsv(_tsv([(95, "w%d" % i) for i in range(60)]))
    assert out.needs_escalation is False


def test_a_low_confidence_page_escalates():
    out = ocr.parse_tesseract_tsv(_tsv([(35, "w%d" % i) for i in range(60)]))
    assert out.needs_escalation is True


def test_is_near_empty_text_thresholds():
    assert ocr.is_near_empty_text("")
    assert ocr.is_near_empty_text("   ")
    assert ocr.is_near_empty_text("short")
    assert not ocr.is_near_empty_text("x" * (ocr.OCR_MIN_CHARS + 1))


def test_ocr_page_via_tesseract_raises_on_missing_binary(monkeypatch, tmp_path):
    import subprocess

    def _boom(*_a, **_k):
        raise FileNotFoundError("tesseract: command not found")

    monkeypatch.setattr(subprocess, "run", _boom)
    try:
        ocr.ocr_page_via_tesseract(b"fake-png-bytes")
    except FileNotFoundError:
        pass
    else:
        raise AssertionError("expected ocr_page_via_tesseract to propagate a missing-binary failure")


def test_ocr_page_via_model_calls_model_backend_run_vision(monkeypatch):
    import model_backend

    calls = []

    def fake_run_vision(image_bytes, prompt, usage=None):
        calls.append((image_bytes, prompt))
        return "transcribed text"

    monkeypatch.setattr(model_backend, "run_vision", fake_run_vision)

    text = ocr.ocr_page_via_model(b"fake-png-bytes")

    assert text == "transcribed text"
    assert calls[0][0] == b"fake-png-bytes"
    assert calls[0][1] == ocr.OCR_TRANSCRIBE_PROMPT


def test_ocr_page_via_model_records_cost_telemetry(monkeypatch):
    import model_backend
    import telemetry_sqlite

    def fake_run_vision(image_bytes, prompt, usage=None):
        usage.update({"prompt_tokens": 1200, "completion_tokens": 40, "cost": 0.00147})
        return "transcribed text"

    monkeypatch.setattr(model_backend, "run_vision", fake_run_vision)
    captured = {}
    monkeypatch.setattr(
        telemetry_sqlite, "record_model_context_event",
        lambda payload: captured.update(payload) or "evt",
    )
    monkeypatch.setenv("CASEFORGE_RUNTIME_LABEL", "rag-extract")

    ocr.ocr_page_via_model(b"fake-png-bytes")

    assert captured["route_label"] == "ocr-escalation"
    assert captured["route_reason"] == "runtime_label=rag-extract"
    assert captured["final_state"] == "completed"
    assert captured["selected_model"] == model_backend.vision_model()
    assert captured["input_tokens"] == 1200
    assert captured["output_tokens"] == 40
    assert captured["estimated_cost_usd"] == 0.00147


def test_ocr_page_via_model_records_failed_telemetry_and_still_raises(monkeypatch):
    import model_backend
    import telemetry_sqlite

    def fake_run_vision(image_bytes, prompt, usage=None):
        raise model_backend.ModelBackendError("openrouter vision call failed: boom")

    monkeypatch.setattr(model_backend, "run_vision", fake_run_vision)
    captured = {}
    monkeypatch.setattr(
        telemetry_sqlite, "record_model_context_event",
        lambda payload: captured.update(payload) or "evt",
    )

    with pytest.raises(model_backend.ModelBackendError):
        ocr.ocr_page_via_model(b"fake-png-bytes")

    assert captured["final_state"] == "failed"
    assert captured["estimated_cost_usd"] == 0.0




def test_ocr_page_uses_tesseract_first_without_calling_the_model(monkeypatch):
    monkeypatch.setattr(ocr, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(
        ocr, "ocr_page_via_tesseract",
        lambda _image_bytes: ocr.TesseractResult(
            text="tesseract transcribed this whole scanned page just fine",
            mean_conf=92.0, word_count=40, low_conf_ratio=0.0,
        ),
    )

    def _boom(*_a, **_k):
        raise AssertionError("the vision model must not run when tesseract already succeeded")

    monkeypatch.setattr(ocr, "ocr_page_via_model", _boom)

    assert ocr.ocr_page(b"fake-png-bytes") == "tesseract transcribed this whole scanned page just fine"


def test_ocr_page_escalates_to_the_model_on_low_tesseract_confidence(monkeypatch):
    monkeypatch.setattr(ocr, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(ocr, "OCR_FALLBACK_ENABLED", True)
    monkeypatch.setattr(
        ocr, "ocr_page_via_tesseract",
        lambda _image_bytes: ocr.TesseractResult(text="", mean_conf=0.0, word_count=0, low_conf_ratio=1.0),
    )
    monkeypatch.setattr(ocr, "ocr_page_via_model", lambda _image_bytes: "the model transcribed the handwriting")

    assert ocr.ocr_page(b"fake-png-bytes") == "the model transcribed the handwriting"


def test_ocr_page_reports_failures_via_the_callback_not_an_exception(monkeypatch):
    monkeypatch.setattr(ocr, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(ocr, "OCR_FALLBACK_ENABLED", True)
    monkeypatch.setattr(ocr, "ocr_page_via_tesseract", lambda _i: (_ for _ in ()).throw(RuntimeError("tesseract died")))
    monkeypatch.setattr(ocr, "ocr_page_via_model", lambda _i: (_ for _ in ()).throw(RuntimeError("model died too")))
    reasons = []

    result = ocr.ocr_page(b"fake-png-bytes", on_failure=reasons.append)

    assert result == ""
    assert any("tesseract died" in r for r in reasons)
    assert any("model died too" in r for r in reasons)




def _pdf_with_text_and_blank_page() -> bytes:
    from io import BytesIO
    from reportlab.pdfgen import canvas as rl_canvas

    buf = BytesIO()
    c = rl_canvas.Canvas(buf)
    c.drawString(72, 700, "Hello World Page One has more than forty characters of real text.")
    c.showPage()
    c.showPage()
    c.save()
    return buf.getvalue()


def test_read_pdf_text_defaults_to_unbounded_pages(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_FALLBACK_ENABLED", False)
    monkeypatch.setattr(ocr, "TESSERACT_AVAILABLE", False)

    text, used_ocr = ocr.read_pdf_text_with_ocr_fallback(_pdf_with_text_and_blank_page())

    assert "Hello World Page One" in text
    assert used_ocr is False


def test_read_pdf_text_reports_used_ocr_only_when_a_page_actually_needed_it(monkeypatch):
    monkeypatch.setattr(ocr, "OCR_FALLBACK_ENABLED", True)
    monkeypatch.setattr(ocr, "rasterize_pdf_page", lambda *_a, **_k: b"fake-png-bytes")
    monkeypatch.setattr(ocr, "ocr_page_via_model", lambda _i: "the scanned page's transcribed content here")

    text, used_ocr = ocr.read_pdf_text_with_ocr_fallback(_pdf_with_text_and_blank_page())

    assert "the scanned page's transcribed content here" in text
    assert used_ocr is True


def test_read_pdf_text_max_pages_caps_how_many_pages_are_read():
    text, _used_ocr = ocr.read_pdf_text_with_ocr_fallback(_pdf_with_text_and_blank_page(), max_pages=1)

    assert "Hello World Page One" in text


def test_read_pdf_text_raises_a_clear_error_when_pypdf_is_missing(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "pypdf":
            raise ImportError("no module named pypdf")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="pypdf is required"):
        ocr.read_pdf_text_with_ocr_fallback(b"whatever")



import io
import random
import shutil

PIL_Image = pytest.importorskip("PIL.Image")
from PIL import Image, ImageDraw, ImageFont

_PAGE_W, _PAGE_H = 1240, 1754


def _level_text_page(*, lines=44, sideways=False):
    img = Image.new("L", (_PAGE_W, _PAGE_H), 255)
    d = ImageDraw.Draw(img)
    rnd = random.Random(3)
    for i in range(lines):
        x = 130
        while x < _PAGE_W - 130:
            length = 40 + int(rnd.random() * 70)
            box = [x, 150 + i * 36, min(x + length, _PAGE_W - 130), 150 + i * 36 + 12]
            d.rectangle([box[1], box[0], box[3], box[2]] if sideways else box, fill=30)
            x += length + 14
    return img


def _tilted(img, downhill_degrees):
    return img.rotate(-downhill_degrees, resample=Image.BICUBIC, fillcolor=255)


def _png(img):
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


@pytest.mark.parametrize("tilt", [-14, -12, -10, -9.5, -9, -5, -2, -1.4, -0.9, 0.9, 1.4, 2, 5, 9, 9.5, 10, 12, 14])
def test_estimate_page_tilt_finds_the_tilt_either_way(tilt):
    angle, prominence, _ink = ocr.estimate_page_tilt(_tilted(_level_text_page(), tilt))
    assert prominence >= ocr._TILT_MIN_PROMINENCE, f"prominence {prominence:.1f}"
    assert abs(angle - tilt) <= 0.15, f"tilt {tilt}: estimated {angle}"


def test_a_level_page_is_returned_untouched():
    png = _png(_level_text_page())
    assert ocr.straighten_page_image(png) is png


def test_a_page_with_few_lines_is_still_measured():
    angle, prominence, _ = ocr.estimate_page_tilt(_tilted(_level_text_page(lines=8), -2))
    assert prominence >= ocr._TILT_MIN_PROMINENCE
    assert abs(angle + 2) <= 0.2


def test_pages_with_nothing_to_level_are_returned_untouched():
    rnd = random.Random(9)
    blank = Image.new("L", (_PAGE_W, _PAGE_H), 255)
    px = blank.load()
    for _ in range(_PAGE_W * _PAGE_H // 60):
        px[rnd.randrange(_PAGE_W), rnd.randrange(_PAGE_H)] = 255 - rnd.randrange(60)
    photo = Image.effect_noise((_PAGE_W, _PAGE_H), 60).point(lambda v: 60 + v // 2)
    sideways = _level_text_page(sideways=True)
    for name, img in (("blank", blank), ("photograph", photo), ("text on its side", sideways)):
        png = _png(img)
        assert ocr.straighten_page_image(png) is png, name


def test_a_tilt_beyond_the_range_searched_is_unknown_not_guessed():
    png = _png(_tilted(_level_text_page(), 20))
    assert ocr.straighten_page_image(png) is png


def test_a_page_straightened_by_its_estimate_measures_level():
    for tilt in (-4, 1.4):
        png = _png(_tilted(_level_text_page(), tilt))
        fixed = ocr.straighten_page_image(png)
        assert fixed is not png
        angle, _prom, _ink = ocr.estimate_page_tilt(Image.open(io.BytesIO(fixed)))
        assert abs(angle) <= 0.3, f"tilt {tilt}: still {angle} after straightening"


def test_straightening_never_raises_on_bytes_it_cannot_open():
    assert ocr.straighten_page_image(b"fake-png-bytes") == b"fake-png-bytes"
    assert ocr.straighten_page_image(b"") == b""


def test_straightening_is_skipped_when_switched_off_or_pillow_is_missing(monkeypatch):
    png = _png(_tilted(_level_text_page(), 3))
    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", False)
    assert ocr.straighten_page_image(png) is png
    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", True)
    monkeypatch.setattr(ocr, "_pillow", lambda: None)
    assert ocr.straighten_page_image(png) is png


def test_tesseract_is_given_the_straightened_page_and_the_model_the_original(monkeypatch):
    import subprocess

    original = _png(_tilted(_level_text_page(), 3))
    seen = {}

    def fake_run(cmd, input=None, **_k):
        if "tsv" not in cmd:
            return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Too few characters")
        seen["tesseract_input"] = input
        return subprocess.CompletedProcess(cmd, 0, stdout=_tsv([(95, "word")] * 3).encode(), stderr=b"")

    monkeypatch.setattr(ocr.subprocess, "run", fake_run)
    monkeypatch.setattr(ocr, "TESSERACT_AVAILABLE", True)
    monkeypatch.setattr(ocr, "OCR_FALLBACK_ENABLED", True)
    monkeypatch.setattr(ocr, "ocr_page_via_model", lambda image_bytes: seen.setdefault("model_input", image_bytes) and "from the model")

    assert ocr.ocr_page(original) == "from the model"
    assert seen["tesseract_input"] != original
    angle, _prom, _ink = ocr.estimate_page_tilt(Image.open(io.BytesIO(seen["tesseract_input"])))
    assert abs(angle) <= 0.3
    assert seen["model_input"] == original


_SCAN_LINES = [
    "The court made the following order on the first day of the hearing",
    "Both parties shall file and serve a short statement of their position",
    "The matter is listed for a further directions appointment before a judge",
    "Each party must comply with this order by four pm on the date shown below",
    "Any application to vary or discharge this order must be made on notice",
    "The respondent shall not remove the child from the jurisdiction of England",
]


def _recall(text):
    bag = {}
    for w in text.lower().split():
        bag[w] = bag.get(w, 0) + 1
    truth = " ".join(_SCAN_LINES).lower().split()
    hit = 0
    for w in truth:
        if bag.get(w, 0):
            hit += 1
            bag[w] -= 1
    return hit / len(truth)


def test_a_page_scanned_five_degrees_off_level_is_read_through_the_real_tesseract(monkeypatch):
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract is not installed")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
    except OSError:
        pytest.skip("DejaVu Sans is not installed")
    img = Image.new("L", (1700, 2200), 255)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(_SCAN_LINES):
        d.text((140, 300 + i * 90), line, font=font, fill=0)
    png = _png(_tilted(img, 5))

    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", True)
    straightened = _recall(ocr.ocr_page_via_tesseract(png).text)
    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", False)
    plain = _recall(ocr.ocr_page_via_tesseract(png).text)
    assert straightened >= 0.9, f"straightened: {straightened:.0%}"
    assert plain < 0.5, f"test premise: the same page read straight through is {plain:.0%}"



_GOOD_READ = [(93, "word")] * 40
_POOR_READ = [(20, "x")] * 40


def _osd(clockwise, conf=3.0):
    return ("Page number: 0\nOrientation in degrees: %d\nRotate: %d\nOrientation confidence: %.2f\n"
            "Script: Latin\nScript confidence: 2.00\n" % (clockwise, (360 - clockwise) % 360, conf)).encode()


def _fake_tesseract(monkeypatch, *, osd, read):
    import subprocess

    calls = []

    def fake_run(cmd, input=None, **_k):
        if "tsv" in cmd:
            calls.append("read")
            rows = read(Image.open(io.BytesIO(input)))
            return subprocess.CompletedProcess(cmd, 0, stdout=_tsv(rows).encode(), stderr=b"")
        calls.append("osd")
        if osd is None:
            return subprocess.CompletedProcess(cmd, 1, stdout=b"", stderr=b"Too few characters. Skipping this page")
        return subprocess.CompletedProcess(cmd, 0, stdout=osd, stderr=b"")

    monkeypatch.setattr(ocr.subprocess, "run", fake_run)
    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", True)
    return calls


def _upright_reads_well(img):
    return _GOOD_READ if img.height > img.width else _POOR_READ


_SIDEWAYS = _png(Image.new("L", (300, 200), 255))
_UPRIGHT = _png(Image.new("L", (200, 300), 255))


@pytest.mark.parametrize("clockwise", [0, 90, 180, 270])
def test_the_orientation_detector_answer_is_read(monkeypatch, clockwise):
    _fake_tesseract(monkeypatch, osd=_osd(clockwise), read=_upright_reads_well)
    assert ocr.detect_page_orientation(_SIDEWAYS) == clockwise


def test_an_orientation_detector_that_cannot_tell_means_no_turn(monkeypatch):
    _fake_tesseract(monkeypatch, osd=None, read=_upright_reads_well)
    assert ocr.detect_page_orientation(_SIDEWAYS) == 0
    _fake_tesseract(monkeypatch, osd=b"Page number: 0\nOrientation in degrees: sideways\n", read=_upright_reads_well)
    assert ocr.detect_page_orientation(_SIDEWAYS) == 0
    _fake_tesseract(monkeypatch, osd=b"", read=_upright_reads_well)
    assert ocr.detect_page_orientation(_SIDEWAYS) == 0

    def missing(*_a, **_k):
        raise FileNotFoundError("tesseract")

    monkeypatch.setattr(ocr.subprocess, "run", missing)
    assert ocr.detect_page_orientation(_SIDEWAYS) == 0


@pytest.mark.parametrize("clockwise", [90, 180, 270])
def test_a_turned_page_is_turned_back_exactly(clockwise):
    page = _level_text_page(lines=6)
    turned = page.rotate(-clockwise, expand=True)
    back = Image.open(io.BytesIO(ocr.turn_page_image(_png(turned), clockwise)))
    assert back.size == page.size
    assert back.tobytes() == page.tobytes()


def test_turning_never_raises_on_bytes_it_cannot_open():
    assert ocr.turn_page_image(b"fake-png-bytes", 90) is None


def test_a_page_read_well_never_asks_the_orientation_detector(monkeypatch):
    calls = _fake_tesseract(monkeypatch, osd=_osd(90), read=_upright_reads_well)
    assert not ocr.ocr_page_via_tesseract(_UPRIGHT).needs_escalation
    assert calls == ["read"]


def test_a_poor_read_is_tried_turned_upright_and_the_better_read_kept(monkeypatch):
    calls = _fake_tesseract(monkeypatch, osd=_osd(90), read=_upright_reads_well)
    scored = ocr.ocr_page_via_tesseract(_SIDEWAYS)
    assert calls == ["read", "osd", "read"]
    assert not scored.needs_escalation
    assert scored.mean_conf == 93


def test_a_wrong_guess_loses_to_the_first_read(monkeypatch):
    reads = iter([[(40, "w")] * 40, [(20, "x")] * 40])
    calls = _fake_tesseract(monkeypatch, osd=_osd(180), read=lambda _img: next(reads))
    scored = ocr.ocr_page_via_tesseract(_SIDEWAYS)
    assert calls == ["read", "osd", "read"]
    assert scored.mean_conf == 40


def test_no_second_read_when_switched_off_or_the_detector_cannot_tell(monkeypatch):
    calls = _fake_tesseract(monkeypatch, osd=None, read=_upright_reads_well)
    assert ocr.ocr_page_via_tesseract(_SIDEWAYS).needs_escalation
    assert calls == ["read", "osd"]
    calls = _fake_tesseract(monkeypatch, osd=_osd(90), read=_upright_reads_well)
    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", False)
    assert ocr.ocr_page_via_tesseract(_SIDEWAYS).needs_escalation
    assert calls == ["read"]


@pytest.mark.parametrize("clockwise, lost_as_it_lies", [(90, False), (180, True), (270, True)])
def test_a_page_scanned_on_its_side_is_read_through_the_real_tesseract(monkeypatch, clockwise, lost_as_it_lies):
    if shutil.which("tesseract") is None:
        pytest.skip("tesseract is not installed")
    import subprocess

    langs = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split()
    if "osd" not in langs:
        pytest.skip("tesseract's orientation data (osd.traineddata) is not installed")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
    except OSError:
        pytest.skip("DejaVu Sans is not installed")
    img = Image.new("L", (1700, 2200), 255)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(_SCAN_LINES):
        d.text((140, 300 + i * 90), line, font=font, fill=0)
    png = _png(img.rotate(-clockwise, expand=True))

    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", True)
    turned = _recall(ocr.ocr_page_via_tesseract(png).text)
    monkeypatch.setattr(ocr, "OCR_STRAIGHTEN_ENABLED", False)
    plain = _recall(ocr.ocr_page_via_tesseract(png).text)
    assert turned >= 0.9, f"turned upright: {turned:.0%}"
    assert (plain < 0.5) == lost_as_it_lies, f"test premise: the same page read as it lies is {plain:.0%}"
