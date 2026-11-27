from __future__ import annotations

import hashlib
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MAX_BYTES = 512 * 1024
HASH_RE = re.compile(r"^[0-9a-f]{40}$")
EXTENSIONS = {"png": "image/png", "jpeg": "image/jpeg", "webp": "image/webp", "svg": "image/svg+xml"}
SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"

ALLOWED_ELEMENTS = {
    "svg", "g", "path", "rect", "circle", "ellipse", "line", "polyline", "polygon", "defs", "title", "desc",
    "linearGradient", "radialGradient", "stop", "clipPath", "mask", "text", "tspan", "use", "symbol",
}
ALLOWED_ATTRIBUTES = {
    "id", "class", "d", "x", "y", "x1", "x2", "y1", "y2", "cx", "cy", "r", "rx", "ry", "fx", "fy", "width", "height", "viewBox",
    "points", "transform", "fill", "fill-rule", "fill-opacity", "stroke", "stroke-width", "stroke-linecap", "stroke-linejoin",
    "stroke-opacity", "stroke-miterlimit", "stroke-dasharray", "opacity", "offset", "stop-color", "stop-opacity", "gradientUnits",
    "gradientTransform", "version", "preserveAspectRatio", "clip-path", "clip-rule", "mask", "style", "href", "font-size",
    "font-family", "font-weight", "text-anchor", "role", "aria-label", "aria-hidden", "xmlns", "xml:space", "dx", "dy",
}
_DANGEROUS_VALUE = re.compile(r"javascript:|data:|vbscript:|@import|expression\s*\(|<|&#|\\", re.I)
_URL = re.compile(r"url\(\s*(['\"]?)([^)'\"]*)\1\s*\)", re.I)


class LogoError(ValueError):
    pass


def sniff(data: bytes) -> str:
    if not data:
        raise LogoError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise LogoError(f"The logo is larger than {MAX_BYTES // 1024} KB.")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data.lstrip(b"\xef\xbb\xbf \t\r\n")[:200].lower()
    if head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in data[:2000].lower()):
        return "svg"
    raise LogoError("The logo must be a PNG, JPEG, WebP or plain SVG picture.")


def _local(name: str) -> tuple[str, str]:
    if name.startswith("{"):
        ns, _, local = name[1:].partition("}")
        return ns, local
    return "", name


def _check_value(value: str, attribute: str) -> None:
    if _DANGEROUS_VALUE.search(value):
        raise LogoError(f"The SVG has a value that is not allowed ({attribute}).")
    for match in _URL.finditer(value):
        if not match.group(2).startswith("#"):
            raise LogoError("The SVG refers to something outside the file.")


def sanitise_svg(data: bytes) -> bytes:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        raise LogoError("The SVG must be UTF-8 text.") from None
    lowered = text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered or "<![cdata[" in lowered:
        raise LogoError("The SVG has a DOCTYPE, entity or CDATA section, which is not allowed.")
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        raise LogoError("The SVG could not be read.") from None
    count = 0
    for element in root.iter():
        count += 1
        if count > 5000:
            raise LogoError("The SVG is too complicated for a logo.")
        ns, local = _local(element.tag if isinstance(element.tag, str) else "")
        if ns != SVG_NS or local not in ALLOWED_ELEMENTS:
            raise LogoError(f"The SVG uses an element that is not allowed ({local or 'comment'}).")
        for name, value in list(element.attrib.items()):
            ans, alocal = _local(name)
            if alocal.lower().startswith("on"):
                raise LogoError("The SVG has an event handler, which is not allowed.")
            if ans == XLINK_NS and alocal == "href":
                alocal, ans = "href", ""
            elif ans == "http://www.w3.org/XML/1998/namespace" and alocal == "space":
                alocal, ans = "xml:space", ""
            if ans or alocal not in ALLOWED_ATTRIBUTES:
                raise LogoError(f"The SVG uses an attribute that is not allowed ({alocal}).")
            if alocal == "href" and not value.startswith("#"):
                raise LogoError("The SVG refers to something outside the file.")
            _check_value(value, alocal)
        if element.text and element.tag != f"{{{SVG_NS}}}text" and element.tag != f"{{{SVG_NS}}}tspan" and element.text.strip():
            if _local(element.tag)[1] not in ("title", "desc"):
                raise LogoError("The SVG has text where none is expected.")
    if _local(root.tag)[1] != "svg":
        raise LogoError("The file is not an SVG picture.")
    ET.register_namespace("", SVG_NS)
    return ET.tostring(root, encoding="utf-8")


def prepare(data: bytes) -> tuple[str, bytes]:
    kind = sniff(data)
    if kind == "svg":
        data = sanitise_svg(data)
        if len(data) > MAX_BYTES:
            raise LogoError(f"The logo is larger than {MAX_BYTES // 1024} KB.")
    return kind, data


def store(kind: str, data: bytes, data_dir: Path) -> str:
    digest = hashlib.sha256(data).hexdigest()[:40]
    folder = data_dir / "branding"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{digest}.{kind}"
    if not target.exists():
        tmp = target.with_name(target.name + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, target)
    return digest


def read(digest: str, data_dir: Path) -> tuple[bytes, str] | None:
    if not HASH_RE.match(digest or ""):
        return None
    for kind, content_type in EXTENSIONS.items():
        target = data_dir / "branding" / f"{digest}.{kind}"
        if target.is_file():
            return target.read_bytes(), content_type
    return None
