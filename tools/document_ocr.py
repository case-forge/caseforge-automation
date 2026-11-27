#!/usr/bin/env python3
from __future__ import annotations

import array
import dataclasses
import io
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from flags_env import load_flags_env

load_flags_env()

OCR_FALLBACK_ENABLED = os.environ.get("CASEFORGE_OCR_FALLBACK", "1").strip().lower() not in {"0", "false", "no", "off"}
TESSERACT_AVAILABLE = shutil.which("tesseract") is not None
OCR_MIN_CHARS = int(os.environ.get("CASEFORGE_OCR_MIN_CHARS", "40"))
OCR_MIN_MEAN_CONF = float(os.environ.get("CASEFORGE_OCR_MIN_MEAN_CONF", "60"))
OCR_MIN_WORDS = int(os.environ.get("CASEFORGE_OCR_MIN_WORDS", "8"))
OCR_MAX_LOW_CONF_RATIO = float(os.environ.get("CASEFORGE_OCR_MAX_LOW_CONF_RATIO", "0.5"))
OCR_LOW_CONF_WORD = float(os.environ.get("CASEFORGE_OCR_LOW_CONF_WORD", "60"))

OCR_TRANSCRIBE_PROMPT = (
    "Transcribe every word of visible text in this scanned page image, exactly as written. "
    "Include any handwritten annotation. Where text has been crossed/struck through with a "
    "replacement written nearby (e.g. a corrected address or number in red ink), report both: "
    "'STRUCK: <original> -> REPLACED: <new value>'. Output only the transcribed text, no commentary."
)


@dataclasses.dataclass(frozen=True)
class TesseractResult:

    text: str
    mean_conf: float
    word_count: int
    low_conf_ratio: float

    @property
    def needs_escalation(self) -> bool:
        if self.word_count < OCR_MIN_WORDS:
            return True
        if self.mean_conf < OCR_MIN_MEAN_CONF:
            return True
        return self.low_conf_ratio > OCR_MAX_LOW_CONF_RATIO


def is_near_empty_text(text: str, *, min_chars: int = OCR_MIN_CHARS) -> bool:
    return len(str(text or "").strip()) < min_chars


def parse_tesseract_tsv(tsv: str) -> TesseractResult:
    words: list[str] = []
    confs: list[float] = []
    for line in (tsv or "").splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) < 12:
            continue
        try:
            conf = float(parts[10])
        except ValueError:
            continue
        text = parts[11].strip()
        if conf < 0 or not text:
            continue
        words.append(text)
        confs.append(conf)

    if not confs:
        return TesseractResult(text="", mean_conf=0.0, word_count=0, low_conf_ratio=1.0)

    low = sum(1 for c in confs if c < OCR_LOW_CONF_WORD)
    return TesseractResult(
        text=" ".join(words),
        mean_conf=sum(confs) / len(confs),
        word_count=len(confs),
        low_conf_ratio=low / len(confs),
    )


MAX_RASTER_SIDE_PX = 3000


def _page_exceeds_raster_cap(data: bytes, page_number: int, dpi: int) -> bool:
    try:
        from pypdf import PdfReader

        box = PdfReader(io.BytesIO(data)).pages[page_number - 1].mediabox
        longest_pt = max(abs(float(box.width)), abs(float(box.height)))
    except Exception:
        return True
    return longest_pt / 72 * dpi > MAX_RASTER_SIDE_PX


def rasterize_pdf_page(data: bytes, page_number: int, *, dpi: int = 200) -> bytes:
    with tempfile.TemporaryDirectory(prefix="caseforge-ocr-") as tmp:
        tmp_path = Path(tmp)
        pdf_path = tmp_path / "page.pdf"
        pdf_path.write_bytes(data)
        out_prefix = tmp_path / "page"
        command = ["pdftoppm", "-png", "-r", str(dpi), "-f", str(page_number), "-l", str(page_number)]
        if _page_exceeds_raster_cap(data, page_number, dpi):
            command += ["-scale-to", str(MAX_RASTER_SIDE_PX)]
        result = subprocess.run(command + [str(pdf_path), str(out_prefix)], capture_output=True, timeout=30)
        if result.returncode != 0:
            raise RuntimeError(f"pdftoppm failed: {result.stderr.decode('utf-8', 'replace')[:300]}")
        candidates = sorted(tmp_path.glob("page*.png"))
        if not candidates:
            raise RuntimeError(f"pdftoppm produced no output for page {page_number}")
        return candidates[0].read_bytes()


OCR_STRAIGHTEN_ENABLED = os.environ.get("CASEFORGE_OCR_STRAIGHTEN", "1").strip().lower() not in {"0", "false", "no", "off"}
_TILT_RANGE = 15.0
_TILT_COARSE_STEP = 0.5
_TILT_FINE_STEP = 0.05
_TILT_MIN_PROMINENCE = 20.0
_TILT_MIN_INK = 0.005
_TILT_APPLY_MIN = 0.25


def _pillow():
    try:
        from PIL import Image
        return Image
    except Exception:
        return None


def estimate_page_tilt(image, Image=None) -> tuple[float, float, float]:
    Image = Image or _pillow()
    small = image.convert("L").resize((max(1, image.width // 4), max(1, image.height // 4)), Image.BOX)
    hist = small.histogram()
    target, seen, paper = small.width * small.height * 0.9, 0, 255
    for value, count in enumerate(hist):
        seen += count
        if seen >= target:
            paper = max(value, 1)
            break
    weights = small.point([int(max(0.0, min(1.0, (paper - v) / paper)) * 255) for v in range(256)])
    ink = sum(i * c for i, c in enumerate(weights.histogram())) / 255.0 / (small.width * small.height)
    if ink < _TILT_MIN_INK:
        return 0.0, 0.0, ink

    def sharpness(angle: float) -> float:
        rotated = weights.rotate(angle, resample=Image.BILINEAR, fillcolor=0)
        rows = array.array("f", rotated.convert("F").resize((1, rotated.height), Image.BOX).tobytes())
        return sum((rows[i + 1] - rows[i]) ** 2 for i in range(len(rows) - 1))

    steps = int(round(_TILT_RANGE * 2 / _TILT_COARSE_STEP))
    coarse = {-_TILT_RANGE + k * _TILT_COARSE_STEP: sharpness(-_TILT_RANGE + k * _TILT_COARSE_STEP) for k in range(steps + 1)}
    best = max(coarse, key=coarse.get)
    median = sorted(coarse.values())[len(coarse) // 2]
    prominence = coarse[best] / max(median, 1e-9)
    if abs(best) >= _TILT_RANGE - _TILT_COARSE_STEP:
        return 0.0, prominence, ink
    fine = [best - _TILT_COARSE_STEP + k * _TILT_FINE_STEP for k in range(int(round(2 * _TILT_COARSE_STEP / _TILT_FINE_STEP)) + 1)]
    return round(max(fine, key=sharpness), 2), prominence, ink


def straighten_page_image(image_bytes: bytes) -> bytes:
    if not OCR_STRAIGHTEN_ENABLED:
        return image_bytes
    Image = _pillow()
    if Image is None:
        return image_bytes
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            image = opened.convert("L")
        angle, prominence, _ink = estimate_page_tilt(image, Image)
        if prominence < _TILT_MIN_PROMINENCE or abs(angle) < _TILT_APPLY_MIN:
            return image_bytes
        out = io.BytesIO()
        image.rotate(angle, resample=Image.BICUBIC, fillcolor=255).save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return image_bytes




def detect_page_orientation(image_bytes: bytes) -> int:
    try:
        result = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "0"],
                                input=image_bytes, capture_output=True, timeout=30)
    except Exception:
        return 0
    if result.returncode != 0:
        return 0
    for line in result.stdout.decode("utf-8", "replace").splitlines():
        key, _, value = line.partition(":")
        if key.strip() == "Orientation in degrees":
            try:
                angle = int(value.strip()) % 360
            except ValueError:
                return 0
            return angle if angle in (90, 180, 270) else 0
    return 0


def turn_page_image(image_bytes: bytes, clockwise: int) -> "bytes | None":
    Image = _pillow()
    if Image is None:
        return None
    try:
        with Image.open(io.BytesIO(image_bytes)) as opened:
            out = io.BytesIO()
            opened.rotate(clockwise, expand=True).save(out, format="PNG")
        return out.getvalue()
    except Exception:
        return None


def _confident_words(scored: TesseractResult) -> float:
    return scored.word_count * (1.0 - scored.low_conf_ratio)


def _read_with_tesseract(image_bytes: bytes) -> TesseractResult:
    result = subprocess.run(
        ["tesseract", "stdin", "stdout", "tsv"],
        input=image_bytes, capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"tesseract failed: {result.stderr.decode('utf-8', 'replace')[:300]}")
    return parse_tesseract_tsv(result.stdout.decode("utf-8", "replace"))


def ocr_page_via_tesseract(image_bytes: bytes) -> TesseractResult:
    scored = _read_with_tesseract(straighten_page_image(image_bytes))
    if not scored.needs_escalation or not OCR_STRAIGHTEN_ENABLED:
        return scored
    clockwise = detect_page_orientation(image_bytes)
    turned = turn_page_image(image_bytes, clockwise) if clockwise else None
    if turned is None:
        return scored
    try:
        retry = _read_with_tesseract(straighten_page_image(turned))
    except Exception:
        return scored
    return retry if _confident_words(retry) > _confident_words(scored) else scored


def _record_ocr_escalation_telemetry(usage: dict, *, model: str, final_state: str, elapsed: float) -> None:
    try:
        import telemetry_sqlite
    except Exception:
        try:
            from tools import telemetry_sqlite
        except Exception:
            return
    raw_usage = usage if isinstance(usage, dict) else {}
    prompt_details = raw_usage.get("prompt_tokens_details") or {}
    payload = {
        "selected_model": model,
        "provider": "openrouter",
        "route_label": "ocr-escalation",
        "route_reason": f"runtime_label={os.getenv('CASEFORGE_RUNTIME_LABEL', 'unspecified-runtime')}",
        "final_state": final_state,
        "input_tokens": int(raw_usage.get("prompt_tokens") or 0),
        "output_tokens": int(raw_usage.get("completion_tokens") or 0),
        "cache_read_tokens": int(prompt_details.get("cached_tokens") or 0),
        "cache_creation_tokens": int(prompt_details.get("cache_write_tokens") or 0),
        "estimated_cost_usd": float(raw_usage.get("cost") or 0.0),
        "elapsed_seconds": round(elapsed, 4),
    }
    try:
        telemetry_sqlite.record_model_context_event(payload)
    except Exception:
        pass


def ocr_page_via_model(image_bytes: bytes, prompt: str = OCR_TRANSCRIBE_PROMPT) -> str:
    import model_backend

    usage: dict = {}
    started = time.monotonic()
    try:
        text = model_backend.run_vision(image_bytes, prompt, usage=usage)
    except Exception:
        _record_ocr_escalation_telemetry(
            usage, model=model_backend.vision_model(), final_state="failed",
            elapsed=time.monotonic() - started,
        )
        raise
    if usage:
        print(
            f"[document_ocr] OCR escalation: "
            f"in={usage.get('prompt_tokens', 0)} out={usage.get('completion_tokens', 0)}",
            file=sys.stderr,
        )
    _record_ocr_escalation_telemetry(
        usage, model=model_backend.vision_model(), final_state="completed",
        elapsed=time.monotonic() - started,
    )
    return text


def ocr_page(image_bytes: bytes, *, on_failure: "Callable[[str], None] | None" = None) -> str:
    text = ""
    escalate = True
    if TESSERACT_AVAILABLE:
        try:
            scored = ocr_page_via_tesseract(image_bytes)
            text = scored.text
            escalate = scored.needs_escalation
        except Exception as exc:
            if on_failure:
                on_failure(f"tesseract failed: {exc}")
    if not escalate:
        return text
    if not OCR_FALLBACK_ENABLED:
        if on_failure:
            on_failure("low-quality OCR, escalation disabled")
        return text
    try:
        return ocr_page_via_model(image_bytes)
    except Exception as exc:
        if on_failure:
            on_failure(f"escalation failed: {exc}")
        return text


def read_pdf_text_with_ocr_fallback(
    data: bytes,
    *,
    max_pages: "int | None" = None,
    on_failure: "Callable[[str, int], None] | None" = None,
) -> tuple[str, bool]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to read .pdf files") from exc

    reader = PdfReader(io.BytesIO(data))
    pages: list[str] = []
    used_ocr = False
    for idx, page in enumerate(reader.pages[:max_pages]):
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if is_near_empty_text(page_text) and (TESSERACT_AVAILABLE or OCR_FALLBACK_ENABLED):
            page_number = idx + 1
            try:
                image_bytes = rasterize_pdf_page(data, page_number)
                ocr_text = ocr_page(
                    image_bytes,
                    on_failure=(lambda reason, _pn=page_number: on_failure(reason, _pn)) if on_failure else None,
                )
                if not is_near_empty_text(ocr_text):
                    page_text = ocr_text
                    used_ocr = True
                elif on_failure:
                    on_failure("OCR ran but produced no usable text (page may be blank or unreadable)", page_number)
            except Exception as exc:
                if on_failure:
                    on_failure(str(exc), page_number)
        pages.append(page_text)
    return "\n".join(pages), used_ocr
