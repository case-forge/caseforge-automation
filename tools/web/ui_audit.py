#!/usr/bin/env python3
"Audit a *rendered* page for the UI defects this estate actually ships."
from __future__ import annotations

import argparse
import json
import math
import re
import sys

LEVEL_ORDER = {"FAIL": 0, "WARN": 1, "INFO": 2, "PASS": 3}

CONTRAST_AA_NORMAL = 4.5
CONTRAST_AA_LARGE = 3.0
LARGE_TEXT_PX = 24.0
LARGE_TEXT_BOLD_PX = 18.66

SHADOW_MIN_CONTRAST = 1.10

_NUM = r"[-+]?[0-9]*\.?[0-9]+"




def _oklch_to_srgb(lightness: float, chroma: float, hue_deg: float) -> tuple[float, float, float]:
    "Convert OKLCH to sRGB 0-255."
    hue_rad = math.radians(hue_deg)
    a_star = chroma * math.cos(hue_rad)
    b_star = chroma * math.sin(hue_rad)

    l_ = lightness + 0.3963377774 * a_star + 0.2158037573 * b_star
    m_ = lightness - 0.1055613458 * a_star - 0.0638541728 * b_star
    s_ = lightness - 0.0894841775 * a_star - 1.2914855480 * b_star
    long_, med, short = l_ ** 3, m_ ** 3, s_ ** 3

    linear = (
        4.0767416621 * long_ - 3.3077115913 * med + 0.2309699292 * short,
        -1.2684380046 * long_ + 2.6097574011 * med - 0.3413193965 * short,
        -0.0041960863 * long_ - 0.7034186147 * med + 1.7076147010 * short,
    )

    out = []
    for channel in linear:
        clamped = max(0.0, min(1.0, channel))
        gamma = 12.92 * clamped if clamped <= 0.0031308 else 1.055 * (clamped ** (1 / 2.4)) - 0.055
        out.append(max(0.0, min(255.0, gamma * 255.0)))
    return (out[0], out[1], out[2])


def parse_color(value: str) -> tuple[float, float, float, float] | None:
    "Parse a CSS colour into (r, g, b, a) with r/g/b in 0-255 and a in 0-1."
    if not value:
        return None
    text = value.strip().lower()
    if text in {"none", "currentcolor", "inherit", "initial"}:
        return None
    if text == "transparent":
        return (0.0, 0.0, 0.0, 0.0)

    oklch = re.match(
        rf"oklch\(\s*({_NUM})(%?)\s+({_NUM})(%?)\s+({_NUM})(?:deg)?\s*(?:/\s*({_NUM}%?)\s*)?\)", text
    )
    if oklch:
        light_raw, light_pct, chroma_raw, chroma_pct, hue, alpha = oklch.groups()
        lightness = float(light_raw) / 100.0 if light_pct else float(light_raw)
        chroma = float(chroma_raw) / 100.0 * 0.4 if chroma_pct else float(chroma_raw)
        red, green, blue = _oklch_to_srgb(lightness, chroma, float(hue))
        if alpha is None:
            alpha_value = 1.0
        elif alpha.endswith("%"):
            alpha_value = float(alpha[:-1]) / 100.0
        else:
            alpha_value = float(alpha)
        return (red, green, blue, max(0.0, min(1.0, alpha_value)))

    match = re.match(rf"rgba?\(\s*({_NUM})\s*[, ]\s*({_NUM})\s*[, ]\s*({_NUM})\s*(?:[,/]\s*({_NUM}%?)\s*)?\)", text)
    if not match:
        return None
    red, green, blue, alpha = match.groups()
    if alpha is None:
        alpha_value = 1.0
    elif alpha.endswith("%"):
        alpha_value = float(alpha[:-1]) / 100.0
    else:
        alpha_value = float(alpha)
    return (float(red), float(green), float(blue), max(0.0, min(1.0, alpha_value)))


def _is_unparseable_color(raw: str) -> bool:
    "True when a background declares a colour we could not understand."
    if not raw:
        return False
    text = raw.strip().lower()
    if text in {"none", "transparent", "currentcolor", "inherit", "initial", ""}:
        return False
    return parse_color(text) is None


def composite(top: tuple[float, float, float, float], under: tuple[float, float, float]) -> tuple[float, float, float]:
    "Alpha-composite `top` over an opaque `under`, returning an opaque colour."
    alpha = top[3]
    return (
        top[0] * alpha + under[0] * (1 - alpha),
        top[1] * alpha + under[1] * (1 - alpha),
        top[2] * alpha + under[2] * (1 - alpha),
    )


def relative_luminance(rgb: tuple[float, float, float]) -> float:
    "WCAG 2.x relative luminance."
    channels = []
    for raw in rgb:
        srgb = raw / 255.0
        channels.append(srgb / 12.92 if srgb <= 0.04045 else ((srgb + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast_ratio(first: tuple[float, float, float], second: tuple[float, float, float]) -> float:
    "WCAG contrast ratio between two opaque colours (1.0 - 21.0)."
    lum_a, lum_b = relative_luminance(first), relative_luminance(second)
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)




def gradient_stops(background_image: str) -> list[tuple[float, float, float, float]]:
    "Extract colour stops from a CSS gradient."
    if not background_image or background_image.strip().lower() == "none":
        return []
    if "gradient" not in background_image.lower():
        return []
    found = re.findall(r"(?:rgba?|oklch)\([^)]*\)", background_image)
    return [c for c in (parse_color(m) for m in found) if c]


def has_bitmap_background(background_image: str) -> bool:
    "True when the background is an image whose colour we cannot know."
    if not background_image or background_image.strip().lower() == "none":
        return False
    return "url(" in background_image.lower() and "gradient" not in background_image.lower()


def resolve_effective_background(chain: list[dict]) -> tuple[str, object]:
    "Resolve what an element is *actually* painted on."
    stack: list[tuple[float, float, float, float]] = []

    for layer in chain:
        image = layer.get("backgroundImage", "") or ""
        if has_bitmap_background(image):
            return ("unknown", "background is a bitmap image; colour not derivable from computed styles")

        raw_color = layer.get("backgroundColor", "") or ""

        if _is_unparseable_color(raw_color):
            return ("unknown", f"background colour {raw_color!r} is in an unsupported colour syntax")
        if image and image.strip().lower() != "none" and "gradient" in image.lower() and not gradient_stops(image):
            return ("unknown", "gradient stops are in an unsupported colour syntax")

        stops = gradient_stops(image)
        if stops:
            darkest = min(stops, key=lambda c: relative_luminance((c[0], c[1], c[2])))
            stack.append(darkest)
            if darkest[3] >= 0.999:
                break

        color = parse_color(raw_color)
        if color and color[3] > 0:
            stack.append(color)
            if color[3] >= 0.999:
                break

    if not stack:
        return ("color", (255.0, 255.0, 255.0))

    base = stack[-1]
    result = (base[0], base[1], base[2])
    if base[3] < 0.999:
        result = composite(base, (255.0, 255.0, 255.0))
    for layer_color in reversed(stack[:-1]):
        result = composite(layer_color, result)
    return ("color", result)




def parse_shadow_layers(box_shadow: str) -> list[dict]:
    "Split a computed `box-shadow` into its layers."
    if not box_shadow or box_shadow.strip().lower() == "none":
        return []

    parts, depth, current = [], 0, ""
    for char in box_shadow:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current)

    layers = []
    for part in parts:
        text = part.strip()
        if not text:
            continue
        color_match = re.search(r"rgba?\([^)]*\)", text)
        color = parse_color(color_match.group(0)) if color_match else None
        lengths = [float(n) for n in re.findall(rf"({_NUM})px", text)]
        has_geometry = any(abs(value) > 0.01 for value in lengths)
        layers.append(
            {
                "raw": text,
                "color": color,
                "has_geometry": has_geometry,
                "inset": "inset" in text.lower(),
            }
        )
    return layers


def visible_shadow_layers(box_shadow: str) -> list[dict]:
    "Layers that actually paint: non-zero alpha AND non-zero geometry."
    return [
        layer
        for layer in parse_shadow_layers(box_shadow)
        if layer["color"] is not None and layer["color"][3] > 0.01 and layer["has_geometry"]
    ]




def judge_contrast(element: dict) -> list[tuple[str, str, str]]:
    "Text contrast against the *effective* background."
    text = (element.get("text") or "").strip()
    if not text:
        return []

    foreground = parse_color(element.get("color", "") or "")
    if foreground is None:
        return []

    kind, background = resolve_effective_background(element.get("bgChain") or [])
    label = element.get("selector", "?")
    snippet = text[:40].replace("\n", " ")

    if kind == "unknown":
        return [("INFO", "contrast", f"{label}: not derivable — {background} (text {snippet!r})")]

    composited = composite(foreground, background) if foreground[3] < 0.999 else (foreground[0], foreground[1], foreground[2])
    ratio = contrast_ratio(composited, background)

    size = float(element.get("fontSizePx") or 16.0)
    weight = float(element.get("fontWeight") or 400)
    is_large = size >= LARGE_TEXT_PX or (size >= LARGE_TEXT_BOLD_PX and weight >= 700)
    threshold = CONTRAST_AA_LARGE if is_large else CONTRAST_AA_NORMAL

    if ratio < threshold:
        return [
            (
                "FAIL",
                "contrast",
                f"{label}: {ratio:.2f}:1 (needs {threshold}:1) text {snippet!r}",
            )
        ]
    return []


def judge_shadow(element: dict) -> list[tuple[str, str, str]]:
    "A shadow that cannot be seen against what it sits on."
    box_shadow = element.get("boxShadow", "") or ""
    layers = visible_shadow_layers(box_shadow)
    if not layers:
        return []

    kind, background = resolve_effective_background(element.get("bgChain") or [])
    if kind == "unknown":
        return []

    label = element.get("selector", "?")
    best = 0.0
    for layer in layers:
        color = layer["color"]
        composited = composite(color, background)
        best = max(best, contrast_ratio(composited, background))

    if best < SHADOW_MIN_CONTRAST:
        return [
            (
                "WARN",
                "dead-shadow",
                f"{label}: shadow contrast {best:.3f} against its backdrop — declared but effectively invisible",
            )
        ]
    return []


def is_screen_reader_only(element: dict) -> bool:
    "True for the visually-hidden idiom (Tailwind `sr-only` and equivalents)."
    clip = (element.get("clip") or "").replace(" ", "")
    clip_path = (element.get("clipPath") or "").replace(" ", "")
    clipped = clip in {"rect(0px,0px,0px,0px)", "rect(0,0,0,0)"} or clip_path == "inset(50%)"
    if not clipped:
        return False
    width = element.get("rectWidth")
    height = element.get("rectHeight")
    if not isinstance(width, (int, float)) or not isinstance(height, (int, float)):
        return False
    return width <= 2 and height <= 2


def judge_invisible_control(element: dict) -> list[tuple[str, str, str]]:
    "A control whose text is invisible against its own background."
    if not element.get("isControl"):
        return []

    if is_screen_reader_only(element):
        if element.get("hasVisibleSibling"):
            return []
        return [
            (
                "FAIL",
                "invisible-control",
                f"{element.get('selector', '?')}: visually hidden with no visible affordance beside it",
            )
        ]

    if not (element.get("text") or "").strip():
        return []

    foreground = parse_color(element.get("color", "") or "")
    if foreground is None:
        return []
    if foreground[3] < 0.05:
        return [("FAIL", "invisible-control", f"{element.get('selector', '?')}: text alpha {foreground[3]:.2f}")]

    kind, background = resolve_effective_background(element.get("bgChain") or [])
    if kind == "unknown":
        return []
    composited = composite(foreground, background) if foreground[3] < 0.999 else (foreground[0], foreground[1], foreground[2])
    ratio = contrast_ratio(composited, background)
    if ratio < CONTRAST_AA_LARGE:
        return [
            (
                "FAIL",
                "invisible-control",
                f"{element.get('selector', '?')}: control text {ratio:.2f}:1 against its own background",
            )
        ]
    return []


def judge_overflow(width: int, scroll_width: int, client_width: int) -> list[tuple[str, str, str]]:
    "Horizontal overflow at a given viewport width."
    if scroll_width > client_width + 1:
        return [
            (
                "FAIL",
                "overflow-x",
                f"{width}px viewport: content is {scroll_width}px wide vs {client_width}px available",
            )
        ]
    return [("PASS", "overflow-x", f"{width}px viewport: no horizontal overflow")]


WASH_COVER_MIN_WIDTH_SHARE = 0.7
WASH_COVER_MIN_HEIGHT_SHARE = 0.5
TAP_TARGET_MIN_PX = 24
TAP_TARGET_COMFORT_PX = 44
PHONE_MAX_WIDTH = 480
_MAX_LISTED = 6


def _has_painted_gradient(background_image: str) -> bool:
    return "gradient(" in (background_image or "")


def _looks_like_a_card(box: dict) -> bool:
    "A panel is meant to stand out from the page: rounded, bordered or shadowed. A column is none of these."
    def px(value: str) -> float:
        match = re.match(_NUM, value or "0")
        return float(match.group(0)) if match else 0.0

    has_shadow = bool(visible_shadow_layers(box.get("boxShadow", "") or ""))
    return px(box.get("borderRadius", "0")) > 0 or px(box.get("borderWidth", "0")) > 0 or has_shadow


def judge_wash_cover(width: int, body_image: str, covers: list[dict]) -> list[tuple[str, str, str]]:
    "A page column that paints its own colour over the body's top wash."
    if not _has_painted_gradient(body_image):
        return []
    hits = []
    for box in covers:
        colour = parse_color(box.get("backgroundColor", ""))
        if colour is None or colour[3] < 0.5 or _has_painted_gradient(box.get("backgroundImage", "")):
            continue
        if _looks_like_a_card(box) or box.get("widthShare", 1) < WASH_COVER_MIN_WIDTH_SHARE:
            continue
        hits.append(box.get("selector", "?"))
    if not hits:
        return [("PASS", "wash-cover", f"{width}px viewport: nothing paints over the page wash")]
    return [
        (
            "WARN",
            "wash-cover",
            f"{width}px viewport: {', '.join(hits[:_MAX_LISTED])} paints an opaque colour over the body's top wash "
            "(remove its own background so the page shows through)",
        )
    ]


def judge_row_overflow(width: int, rows: list[dict]) -> list[tuple[str, str, str]]:
    "A flex row whose children run out of it instead of wrapping or scrolling."
    hits = []
    for row in rows:
        if row.get("flexWrap") != "nowrap" or row.get("overflowX") not in ("visible", "clip"):
            continue
        if row.get("scrollWidth", 0) > row.get("clientWidth", 0) + 1:
            hits.append(f"{row.get('selector', '?')} ({row['scrollWidth']}px in {row['clientWidth']}px)")
    if not hits:
        return [("PASS", "row-overflow", f"{width}px viewport: no flex row runs out of its box")]
    return [
        (
            "WARN",
            "row-overflow",
            f"{width}px viewport: {'; '.join(hits[:_MAX_LISTED])} run out of their box (add flex-wrap or let the row scroll)",
        )
    ]


def judge_tap_targets(width: int, targets: list[dict]) -> list[tuple[str, str, str]]:
    "Controls too small to press on a phone. Phone widths only; inline links in text are exempt."
    if width > PHONE_MAX_WIDTH:
        return []
    small = [t for t in targets if min(t.get("width", 0), t.get("height", 0)) < TAP_TARGET_MIN_PX]
    cramped = [t for t in targets if TAP_TARGET_MIN_PX <= min(t.get("width", 0), t.get("height", 0)) < TAP_TARGET_COMFORT_PX]
    findings: list[tuple[str, str, str]] = []
    if small:
        names = [f"{t.get('selector', '?')} ({round(t['width'])}x{round(t['height'])})" for t in small[:_MAX_LISTED]]
        findings.append(
            ("WARN", "tap-target", f"{width}px viewport: {len(small)} controls under {TAP_TARGET_MIN_PX}px: {'; '.join(names)}")
        )
    else:
        findings.append(("PASS", "tap-target", f"{width}px viewport: every control is at least {TAP_TARGET_MIN_PX}px"))
    if cramped:
        findings.append(
            ("INFO", "tap-target", f"{width}px viewport: {len(cramped)} controls between {TAP_TARGET_MIN_PX} and {TAP_TARGET_COMFORT_PX}px")
        )
    return findings


def judge_images(images: list[dict]) -> list[tuple[str, str, str]]:
    "Images that failed to load."
    findings = []
    for image in images:
        if not image.get("naturalWidth"):
            findings.append(("FAIL", "broken-image", f"{image.get('src', '?')}: naturalWidth 0"))
    if not findings and images:
        findings.append(("PASS", "broken-image", f"{len(images)} image(s) loaded"))
    return findings


def judge_links(link_results: list[dict]) -> list[tuple[str, str, str]]:
    "Internal links that do not resolve."
    findings = []
    for link in link_results:
        status = link.get("status")
        if status is None or status >= 400:
            findings.append(("FAIL", "dead-link", f"{link.get('href', '?')} -> {status}"))
    if not findings and link_results:
        findings.append(("PASS", "dead-link", f"{len(link_results)} internal link(s) resolve"))
    return findings


def judge_console(messages: list[str]) -> list[tuple[str, str, str]]:
    "Console errors. Cheap to collect and this estate has shipped two silent"
    if messages:
        return [("FAIL", "console-error", msg[:200]) for msg in messages]
    return [("PASS", "console-error", "no console errors")]


def judge_page(payload: dict) -> list[tuple[str, str, str]]:
    "Run every judgement over one extracted page payload."
    findings: list[tuple[str, str, str]] = []
    for element in payload.get("elements", []):
        findings.extend(judge_contrast(element))
        findings.extend(judge_shadow(element))
        findings.extend(judge_invisible_control(element))
    for measurement in payload.get("overflow", []):
        findings.extend(
            judge_overflow(measurement["width"], measurement["scrollWidth"], measurement["clientWidth"])
        )
    for layout in payload.get("layout", []):
        findings.extend(judge_wash_cover(layout["width"], layout.get("bodyImage", ""), layout.get("covers", [])))
        findings.extend(judge_row_overflow(layout["width"], layout.get("rows", [])))
        findings.extend(judge_tap_targets(layout["width"], layout.get("tapTargets", [])))
    findings.extend(judge_images(payload.get("images", [])))
    findings.extend(judge_links(payload.get("links", [])))
    findings.extend(judge_console(payload.get("console", [])))
    return findings



EXTRACT_JS = r"""
() => {
  const MAX = 400;
  const selectorFor = (el) => {
    const id = el.id ? `#${el.id}` : "";
    const cls = (el.className && typeof el.className === "string")
      ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".")
      : "";
    return `${el.tagName.toLowerCase()}${id}${cls}`.slice(0, 80);
  };
  // Background chain: the element's own computed background first, then each
  // ancestor outward. BOTH backgroundColor and backgroundImage are captured --
  // capturing only the former is the bug this tool exists to not have.
  const bgChain = (el) => {
    const chain = [];
    let node = el;
    while (node && node.nodeType === 1) {
      const cs = getComputedStyle(node);
      chain.push({
        backgroundColor: cs.backgroundColor,
        backgroundImage: cs.backgroundImage,
      });
      node = node.parentElement;
    }
    return chain;
  };
  const CONTROL = new Set(["BUTTON", "A", "INPUT", "SELECT", "TEXTAREA", "LABEL", "SUMMARY"]);
  const out = [];
  const all = Array.from(document.querySelectorAll("body *")).slice(0, 4000);
  for (const el of all) {
    if (out.length >= MAX) break;
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden" || parseFloat(cs.opacity) === 0) continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    // Only elements with their own direct text, so a wrapper is not judged on
    // its descendants' text.
    const ownText = Array.from(el.childNodes)
      .filter((n) => n.nodeType === 3)
      .map((n) => n.textContent)
      .join("")
      .trim();
    const isControl = CONTROL.has(el.tagName);
    const hasShadow = cs.boxShadow && cs.boxShadow !== "none";
    if (!ownText && !isControl && !hasShadow) continue;
    // A screen-reader-only control is legitimately invisible, but only when
    // something visible stands in for it. A sibling with real area is that
    // stand-in (the Tailwind `peer` pattern styles exactly such a sibling).
    // Captured here rather than inferred later because it needs the live DOM.
    let hasVisibleSibling = false;
    if (el.parentElement) {
      for (const sib of el.parentElement.children) {
        if (sib === el) continue;
        const r = sib.getBoundingClientRect();
        if (r.width > 2 && r.height > 2) { hasVisibleSibling = true; break; }
      }
    }
    out.push({
      selector: selectorFor(el),
      text: ownText,
      color: cs.color,
      fontSizePx: parseFloat(cs.fontSize),
      fontWeight: cs.fontWeight,
      boxShadow: cs.boxShadow,
      isControl,
      clip: cs.clip,
      clipPath: cs.clipPath,
      rectWidth: rect.width,
      rectHeight: rect.height,
      hasVisibleSibling,
      bgChain: bgChain(el),
    });
  }
  const images = Array.from(document.images).slice(0, 100).map((img) => ({
    src: img.currentSrc || img.src,
    naturalWidth: img.naturalWidth,
  }));
  const links = Array.from(document.querySelectorAll("a[href]"))
    .map((a) => a.getAttribute("href"))
    .filter((h) => h && !h.startsWith("#") && !h.startsWith("mailto:") && !h.startsWith("tel:"));
  return { elements: out, images, links: Array.from(new Set(links)).slice(0, 40) };
}
"""


LAYOUT_JS = r"""
() => {
  const vw = document.documentElement.clientWidth;
  const vh = window.innerHeight;
  const selectorFor = (el) => {
    const cls = (el.className && typeof el.className === "string")
      ? "." + el.className.trim().split(/\s+/).slice(0, 2).join(".") : "";
    return `${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${cls}`.slice(0, 80);
  };
  const bodyImage = getComputedStyle(document.body).backgroundImage;
  const covers = [];
  const rows = [];
  const tapTargets = [];
  const seen = new Set();
  const CONTROL = "button, a[href], input:not([type=hidden]), select, textarea, summary, [role=button]";
  for (const el of Array.from(document.querySelectorAll("body *")).slice(0, 4000)) {
    const cs = getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") continue;
    const rect = el.getBoundingClientRect();
    if (rect.width < 1 || rect.height < 1) continue;
    // A page column sits in the flow; a popup or sticky bar does not.
    const inFlow = cs.position === "static" || cs.position === "relative";
    if (inFlow && rect.top + window.scrollY < 360 && rect.width >= vw * 0.5 && rect.height >= vh * 0.5) {
      covers.push({
        selector: selectorFor(el), backgroundColor: cs.backgroundColor, backgroundImage: cs.backgroundImage,
        widthShare: rect.width / vw, borderRadius: cs.borderTopLeftRadius, borderWidth: cs.borderTopWidth,
        boxShadow: cs.boxShadow,
      });
    }
    if ((cs.display === "flex" || cs.display === "inline-flex") && cs.flexDirection.startsWith("row")) {
      rows.push({ selector: selectorFor(el), flexWrap: cs.flexWrap, overflowX: cs.overflowX,
                  scrollWidth: el.scrollWidth, clientWidth: el.clientWidth });
    }
    if (el.matches(CONTROL)) {
      // A link inside running text is exempt (WCAG 2.5.8 inline exception).
      if (el.tagName === "A" && cs.display === "inline") continue;
      const key = selectorFor(el);
      if (seen.has(key)) continue;
      seen.add(key);
      tapTargets.push({ selector: key, width: rect.width, height: rect.height });
    }
  }
  return { width: vw, bodyImage, covers: covers.slice(0, 20), rows: rows.slice(0, 300), tapTargets: tapTargets.slice(0, 300) };
}
"""


def audit(url: str, theme: str = "light", widths: tuple[int, ...] = (1440, 1024, 390), timeout_ms: int = 20000) -> dict:
    "Render `url` and extract everything the judgement layer needs."
    from playwright.sync_api import sync_playwright

    payload: dict = {"url": url, "theme": theme, "console": [], "overflow": [], "links": []}

    with sync_playwright() as play:
        browser = play.chromium.launch(args=["--no-sandbox"])
        try:
            context = browser.new_context(
                color_scheme="dark" if theme == "dark" else "light",
                viewport={"width": widths[0], "height": 900},
            )
            page = context.new_page()
            page.on(
                "console",
                lambda msg: payload["console"].append(f"{msg.type}: {msg.text}") if msg.type == "error" else None,
            )
            page.on("pageerror", lambda err: payload["console"].append(f"pageerror: {err}"))
            page.goto(url, wait_until="networkidle", timeout=timeout_ms)

            if theme == "dark":
                page.evaluate("document.documentElement.setAttribute('data-theme','dark')")
            else:
                page.evaluate("document.documentElement.setAttribute('data-theme','light')")
            page.wait_for_timeout(300)

            extracted = page.evaluate(EXTRACT_JS)
            payload["elements"] = extracted["elements"]
            payload["images"] = extracted["images"]

            for width in widths:
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(150)
                metrics = page.evaluate(
                    "() => ({scrollWidth: document.documentElement.scrollWidth,"
                    " clientWidth: document.documentElement.clientWidth})"
                )
                payload["overflow"].append(
                    {"width": width, "scrollWidth": metrics["scrollWidth"], "clientWidth": metrics["clientWidth"]}
                )
                layout = page.evaluate(LAYOUT_JS)
                layout["width"] = width
                payload.setdefault("layout", []).append(layout)

            from urllib.parse import urljoin, urlparse

            origin = urlparse(url)
            for href in extracted["links"]:
                target = urljoin(url, href)
                if urlparse(target).netloc != origin.netloc:
                    continue
                try:
                    response = page.request.get(target, timeout=timeout_ms)
                    payload["links"].append({"href": href, "status": response.status})
                except Exception as exc:
                    payload["links"].append({"href": href, "status": None, "error": str(exc)[:120]})
        finally:
            browser.close()

    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--theme", choices=("light", "dark", "both"), default="both")
    parser.add_argument("--widths", default="1440,1024,390")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    widths = tuple(int(w) for w in args.widths.split(",") if w.strip())
    themes = ("light", "dark") if args.theme == "both" else (args.theme,)

    results: dict[str, list[tuple[str, str, str]]] = {}
    for theme in themes:
        payload = audit(args.url, theme=theme, widths=widths)
        results[theme] = judge_page(payload)

    if args.json:
        print(json.dumps({t: [{"level": l, "item": i, "detail": d} for l, i, d in f] for t, f in results.items()}, indent=2))
    else:
        for theme, findings in results.items():
            print(f"\n=== {args.url}  [{theme}] ===")
            for level, item, detail in sorted(findings, key=lambda f: LEVEL_ORDER[f[0]]):
                print(f"{level:5} {item:18} {detail}")

    return sum(1 for findings in results.values() for level, _, _ in findings if level == "FAIL")


if __name__ == "__main__":
    sys.exit(main())
