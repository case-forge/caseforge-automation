from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterator

from caseforge_cli.base import CaseforgeCLIError

PASSTHROUGH_SUFFIXES = frozenset({".pdf", ".jpg", ".jpeg", ".png"})

OFFICE_SUFFIXES = frozenset({
    ".doc", ".docx", ".dot", ".dotx", ".dotm", ".rtf", ".odt", ".ods", ".odp",
    ".xls", ".xlsx", ".xlsm", ".ppt", ".pptx", ".pps", ".ppsx",
    ".htm", ".html", ".md", ".markdown", ".eml", ".msg", ".epub",
})

IMAGE_SUFFIXES = frozenset({".tif", ".tiff", ".webp", ".gif", ".bmp", ".heic", ".heif"})

Converter = Callable[[Path, Path], None]


class InputConversionError(CaseforgeCLIError):

    def __init__(self, failed: list[dict[str, str]]):
        names = ", ".join(item["file"] for item in failed)
        super().__init__(
            "input_conversion_failed",
            f"These files could not be converted to PDF for the bundle: {names}.",
            details={"failed": failed},
            tool="bundletool",
        )


@dataclass
class PreparedInputs:

    manifest: dict[str, Any] | str | Path
    docs_dir: Path
    converted: list[dict[str, str]] = field(default_factory=list)


def graph_office_to_pdf(source: Path, output: Path) -> None:
    import graph_files

    from documents.print_email_to_pdf import graph_convert_bytes_to_pdf

    mailbox = os.getenv("GRAPH_MAILBOX_UPN", "").strip()
    if not mailbox:
        raise RuntimeError("GRAPH_MAILBOX_UPN is not set, so Graph has nowhere to render the file")
    output.write_bytes(graph_convert_bytes_to_pdf(mailbox, graph_files.token(), source.suffix.lower(), source.read_bytes()))


def pillow_image_to_pdf(source: Path, output: Path) -> None:
    from PIL import Image, ImageSequence

    if source.suffix.lower() in {".heic", ".heif"}:
        try:
            import pillow_heif
        except ImportError as exc:
            raise RuntimeError("HEIC needs pillow_heif, which is not installed on this machine") from exc
        pillow_heif.register_heif_opener()

    pages = []
    with Image.open(source) as img:
        for frame in ImageSequence.Iterator(img):
            frame = frame.convert("RGBA")
            page = Image.new("RGB", frame.size, "white")
            page.paste(frame, mask=frame.getchannel("A"))
            pages.append(page)
    if not pages:
        raise RuntimeError("the image has no frames")
    pages[0].save(output, "PDF", save_all=True, append_images=pages[1:], resolution=150.0)


def _referenced_names(manifest: dict[str, Any]) -> list[str]:
    names: list[str] = []
    cover = manifest.get("coversheet")
    if isinstance(cover, str) and cover:
        names.append(cover)
    for section in manifest.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for entry in section.get("files") or []:
            if isinstance(entry, dict) and isinstance(entry.get("filename"), str) and entry["filename"]:
                names.append(entry["filename"])
    return list(dict.fromkeys(names))


def _needs_conversion(name: str) -> bool:
    return Path(name).suffix.lower() not in PASSTHROUGH_SUFFIXES


def _load_manifest(manifest: dict[str, Any] | str | Path) -> dict[str, Any] | None:
    if isinstance(manifest, dict):
        return manifest
    try:
        loaded = json.loads(Path(manifest).expanduser().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return loaded if isinstance(loaded, dict) else None


def _pdf_name(name: str, taken: set[str]) -> str:
    stem, suffix = Path(name).stem, Path(name).suffix.lower().lstrip(".")
    candidate = f"{stem}.pdf"
    if candidate in taken:
        candidate = f"{stem} ({suffix}).pdf"
    n = 2
    while candidate in taken:
        candidate = f"{stem} ({suffix} {n}).pdf"
        n += 1
    return candidate


def _place(source: Path, target: Path) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def prepare_inputs(
    manifest: dict[str, Any] | str | Path,
    docs_dir: str | Path,
    staging_dir: str | Path,
    *,
    office_converter: Converter | None = None,
    image_converter: Converter | None = None,
) -> PreparedInputs:
    office_converter = office_converter or graph_office_to_pdf
    image_converter = image_converter or pillow_image_to_pdf
    docs = Path(docs_dir).expanduser()
    loaded = _load_manifest(manifest)
    names = _referenced_names(loaded) if loaded else []
    if not any(_needs_conversion(name) for name in names):
        return PreparedInputs(manifest=manifest, docs_dir=docs)

    staged_docs = Path(staging_dir) / "docs"
    staged_docs.mkdir(parents=True, exist_ok=True)
    taken = {name for name in names if not _needs_conversion(name)}
    renamed: dict[str, str] = {}
    converted: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []

    for name in names:
        source = docs / name
        if Path(name).name != name or not source.is_file():
            renamed[name] = name
            continue
        if not _needs_conversion(name):
            _place(source, staged_docs / name)
            continue
        suffix = source.suffix.lower()
        if suffix in OFFICE_SUFFIXES:
            convert, via = office_converter, "graph"
        elif suffix in IMAGE_SUFFIXES:
            convert, via = image_converter, "image"
        else:
            failed.append({"file": name, "reason": f"no converter for {suffix or 'files with no extension'}"})
            continue
        pdf_name = _pdf_name(name, taken)
        target = staged_docs / pdf_name
        try:
            convert(source, target)
            if not target.is_file() or target.stat().st_size == 0:
                raise RuntimeError("the converter produced no PDF")
        except Exception as exc:
            target.unlink(missing_ok=True)
            failed.append({"file": name, "reason": f"{type(exc).__name__}: {exc}"})
            continue
        taken.add(pdf_name)
        renamed[name] = pdf_name
        converted.append({"file": name, "pdf": pdf_name, "via": via})

    if failed:
        raise InputConversionError(failed)

    new_manifest = json.loads(json.dumps(loaded))
    if isinstance(new_manifest.get("coversheet"), str) and new_manifest["coversheet"] in renamed:
        new_manifest["coversheet"] = renamed[new_manifest["coversheet"]]
    for section in new_manifest.get("sections") or []:
        if not isinstance(section, dict):
            continue
        for entry in section.get("files") or []:
            if not isinstance(entry, dict) or entry.get("filename") not in renamed:
                continue
            original = entry["filename"]
            entry["filename"] = renamed[original]
            title = entry.get("title")
            if Path(renamed[original]).stem != Path(original).stem and (not isinstance(title, str) or not title.strip()):
                entry["title"] = Path(original).stem
    manifest_path = Path(staging_dir) / "manifest.json"
    manifest_path.write_text(json.dumps(new_manifest), encoding="utf-8")
    return PreparedInputs(manifest=manifest_path, docs_dir=staged_docs, converted=converted)


@contextlib.contextmanager
def prepared_inputs(
    manifest: dict[str, Any] | str | Path,
    docs_dir: str | Path,
    **converters: Converter,
) -> Iterator[PreparedInputs]:
    with tempfile.TemporaryDirectory(prefix="bundletool-inputs-") as staging:
        yield prepare_inputs(manifest, docs_dir, staging, **converters)


def render_with_conversion(cli: Any, manifest: dict[str, Any] | str | Path, docs_dir: str | Path, output_path: str | Path, **render_kwargs: Any) -> dict[str, Any]:
    with prepared_inputs(manifest, docs_dir) as prepared:
        result = cli.render(prepared.manifest, prepared.docs_dir, output_path, **render_kwargs)
    if prepared.converted and isinstance(result, dict):
        result = {**result, "converted": prepared.converted}
    return result
