from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "tools" / "web"))

import ui_audit as ua




def naive_background(chain: list[dict]) -> tuple[float, float, float]:
    for layer in chain:
        color = ua.parse_color(layer.get("backgroundColor", ""))
        if color and color[3] > 0:
            return (color[0], color[1], color[2])
    return (255.0, 255.0, 255.0)


def naive_shadow_alpha(box_shadow: str) -> float:
    match = re.search(r"rgba?\([^)]*\)", box_shadow)
    color = ua.parse_color(match.group(0)) if match else None
    return color[3] if color else 0.0



GRADIENT_CHAIN = [
    {"backgroundColor": "rgba(0, 0, 0, 0)", "backgroundImage": "none"},
    {
        "backgroundColor": "rgba(0, 0, 0, 0)",
        "backgroundImage": "linear-gradient(to right, rgb(51, 65, 85), rgb(30, 41, 59))",
    },
    {"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"},
]

WHITE_TEXT_ON_GRADIENT = {
    "selector": "h3.title",
    "text": "Create Bundle",
    "color": "rgb(255, 255, 255)",
    "fontSizePx": 16.0,
    "fontWeight": "400",
    "boxShadow": "none",
    "bgChain": GRADIENT_CHAIN,
}


def test_naive_background_walk_really_does_produce_the_false_positive():
    resolved = naive_background(GRADIENT_CHAIN)
    assert resolved == (255.0, 255.0, 255.0), "naive walk should wrongly resolve to the white ancestor"
    ratio = ua.contrast_ratio((255.0, 255.0, 255.0), resolved)
    assert ratio < 1.05, f"naive walk should report unreadable text; got {ratio:.2f}:1"


def test_gradient_background_is_resolved_and_does_not_flag():
    kind, background = ua.resolve_effective_background(GRADIENT_CHAIN)
    assert kind == "color"
    assert background != (255.0, 255.0, 255.0), "must not fall through to the white ancestor"

    findings = ua.judge_contrast(WHITE_TEXT_ON_GRADIENT)
    assert findings == [], f"white on slate gradient must pass, got {findings}"


def test_gradient_resolution_picks_the_worst_case_stop():
    kind, background = ua.resolve_effective_background(GRADIENT_CHAIN)
    assert kind == "color"
    assert background == (30.0, 41.0, 59.0), "should pick the darker of the two stops"



TAILWIND_SHADOW = "rgba(0, 0, 0, 0) 0px 0px 0px 0px, rgba(0, 0, 0, 0.1) 0px 4px 6px -1px"

CARD_ON_WHITE = {
    "selector": "div.card",
    "text": "",
    "color": "rgb(15, 23, 42)",
    "boxShadow": TAILWIND_SHADOW,
    "bgChain": [{"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"}],
}


def test_naive_shadow_parse_really_does_produce_the_false_positive():
    assert naive_shadow_alpha(TAILWIND_SHADOW) == 0.0, "naive parse should see the zero-alpha placeholder"


def test_tailwind_shadow_is_recognised_as_live_and_does_not_flag():
    layers = ua.visible_shadow_layers(TAILWIND_SHADOW)
    assert len(layers) == 1, f"expected exactly the real layer to survive, got {layers}"
    assert layers[0]["color"][3] == 0.1

    assert ua.judge_shadow(CARD_ON_WHITE) == [], "a real shadow on white must not be flagged"


def test_a_shadow_with_alpha_but_no_geometry_paints_nothing():
    assert ua.visible_shadow_layers("rgba(0, 0, 0, 1) 0px 0px 0px 0px") == []




def test_genuinely_low_contrast_text_is_flagged():
    findings = ua.judge_contrast(
        {
            "selector": "p.muted",
            "text": "Barely there",
            "color": "rgb(200, 200, 200)",
            "fontSizePx": 14.0,
            "fontWeight": "400",
            "boxShadow": "none",
            "bgChain": [{"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"}],
        }
    )
    assert len(findings) == 1 and findings[0][0] == "FAIL"


def test_the_real_bundletool_dead_shadow_is_still_caught():
    findings = ua.judge_shadow(
        {
            "selector": "div.card",
            "boxShadow": TAILWIND_SHADOW,
            "bgChain": [{"backgroundColor": "rgb(2, 6, 23)", "backgroundImage": "none"}],
        }
    )
    assert len(findings) == 1 and findings[0][1] == "dead-shadow", f"got {findings}"


def test_invisible_control_is_flagged():
    findings = ua.judge_invisible_control(
        {
            "selector": "button.theme-toggle",
            "isControl": True,
            "text": "Toggle theme",
            "color": "rgb(250, 250, 250)",
            "bgChain": [{"backgroundColor": "rgb(245, 242, 232)", "backgroundImage": "none"}],
        }
    )
    assert len(findings) == 1 and findings[0][1] == "invisible-control"




def test_bitmap_background_is_reported_unknown_not_failed():
    element = {
        "selector": "h1.hero",
        "text": "Overlaid on a photo",
        "color": "rgb(255, 255, 255)",
        "fontSizePx": 32.0,
        "fontWeight": "700",
        "boxShadow": "none",
        "bgChain": [{"backgroundColor": "rgba(0, 0, 0, 0)", "backgroundImage": 'url("/hero.jpg")'}],
    }
    findings = ua.judge_contrast(element)
    assert len(findings) == 1
    assert findings[0][0] == "INFO", "a bitmap backdrop must be INFO, never FAIL"


def test_shadow_over_bitmap_background_is_silent():
    assert (
        ua.judge_shadow(
            {
                "selector": "div.card",
                "boxShadow": TAILWIND_SHADOW,
                "bgChain": [{"backgroundColor": "rgba(0, 0, 0, 0)", "backgroundImage": 'url("/bg.png")'}],
            }
        )
        == []
    )




def test_parse_color_handles_the_forms_browsers_actually_return():
    assert ua.parse_color("rgb(1, 2, 3)") == (1.0, 2.0, 3.0, 1.0)
    assert ua.parse_color("rgba(1, 2, 3, 0.5)") == (1.0, 2.0, 3.0, 0.5)
    assert ua.parse_color("rgb(1 2 3 / 0.25)") == (1.0, 2.0, 3.0, 0.25)
    assert ua.parse_color("transparent") == (0.0, 0.0, 0.0, 0.0)
    assert ua.parse_color("none") is None


def test_semi_transparent_text_is_composited_before_judging():
    opaque = ua.judge_contrast(
        {
            "selector": "p", "text": "x", "color": "rgb(0, 0, 0)", "fontSizePx": 16.0, "fontWeight": "400",
            "boxShadow": "none",
            "bgChain": [{"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"}],
        }
    )
    faint = ua.judge_contrast(
        {
            "selector": "p", "text": "x", "color": "rgba(0, 0, 0, 0.25)", "fontSizePx": 16.0, "fontWeight": "400",
            "boxShadow": "none",
            "bgChain": [{"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"}],
        }
    )
    assert opaque == [], "solid black on white must pass"
    assert len(faint) == 1 and faint[0][0] == "FAIL", "25% black on white must fail"


def test_large_text_uses_the_lower_threshold():
    element = {
        "selector": "h1", "text": "Heading", "color": "rgb(140, 140, 140)",
        "fontSizePx": 32.0, "fontWeight": "700", "boxShadow": "none",
        "bgChain": [{"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"}],
    }
    assert ua.judge_contrast(element) == [], "3.5:1 passes at large-text size"
    assert len(ua.judge_contrast({**element, "fontSizePx": 14.0, "fontWeight": "400"})) == 1


def test_overflow_and_broken_images_and_dead_links():
    assert ua.judge_overflow(390, 500, 390)[0][0] == "FAIL"
    assert ua.judge_overflow(1440, 1440, 1440)[0][0] == "PASS"
    assert ua.judge_images([{"src": "/a.png", "naturalWidth": 0}])[0][0] == "FAIL"
    assert ua.judge_images([{"src": "/a.png", "naturalWidth": 800}])[0][0] == "PASS"
    assert ua.judge_links([{"href": "/gone", "status": 404}])[0][0] == "FAIL"
    assert ua.judge_links([{"href": "/", "status": 200}])[0][0] == "PASS"


def test_exit_code_counts_only_failures():
    findings = [("FAIL", "a", ""), ("WARN", "b", ""), ("PASS", "c", ""), ("FAIL", "d", "")]
    assert sum(1 for level, _, _ in findings if level == "FAIL") == 2



REAL_BUNDLETOOL_CHAIN = [
    {"backgroundColor": "rgba(0, 0, 0, 0)", "backgroundImage": "none"},
    {
        "backgroundColor": "rgba(0, 0, 0, 0)",
        "backgroundImage": (
            "linear-gradient(to right, oklch(0.372 0.044 257.287) 0%, "
            "oklch(0.279 0.041 260.031) 100%)"
        ),
    },
    {"backgroundColor": "oklch(0.984 0.003 247.858)", "backgroundImage": "none"},
]

REAL_BUNDLETOOL_HEADING = {
    "selector": "h3.text-base.font-bold",
    "text": "Basic Information",
    "color": "rgb(255, 255, 255)",
    "fontSizePx": 16.0,
    "fontWeight": "700",
    "boxShadow": "none",
    "bgChain": REAL_BUNDLETOOL_CHAIN,
}


def test_oklch_parses_to_the_right_srgb():
    for oklch, expected in (
        ("oklch(0.372 0.044 257.287)", (51, 65, 85)),
        ("oklch(0.279 0.041 260.031)", (30, 41, 59)),
        ("oklch(0.984 0.003 247.858)", (248, 250, 252)),
    ):
        parsed = ua.parse_color(oklch)
        assert parsed is not None, f"{oklch} must parse"
        for got, want in zip(parsed[:3], expected):
            assert abs(got - want) <= 4, f"{oklch} -> {parsed[:3]}, expected ~{expected}"


def test_an_rgb_only_parser_really_does_miss_the_oklch_gradient():
    image = REAL_BUNDLETOOL_CHAIN[1]["backgroundImage"]
    assert re.findall(r"rgba?\([^)]*\)", image) == [], "an rgb-only scan should find nothing here"


def test_the_real_bundletool_heading_is_not_flagged():
    kind, background = ua.resolve_effective_background(REAL_BUNDLETOOL_CHAIN)
    assert kind == "color", f"expected a resolved colour, got {kind}: {background}"
    assert background != (255.0, 255.0, 255.0), "must not fall through to white"
    assert ua.judge_contrast(REAL_BUNDLETOOL_HEADING) == []




def test_unparseable_background_colour_stops_the_walk_as_unknown():
    chain = [
        {"backgroundColor": "rgba(0, 0, 0, 0)", "backgroundImage": "none"},
        {"backgroundColor": "lab(54% 81 70)", "backgroundImage": "none"},
        {"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"},
    ]
    kind, reason = ua.resolve_effective_background(chain)
    assert kind == "unknown", f"expected unknown, got {kind}: {reason}"

    findings = ua.judge_contrast(
        {
            "selector": "p", "text": "hello", "color": "rgb(255, 255, 255)",
            "fontSizePx": 16.0, "fontWeight": "400", "boxShadow": "none", "bgChain": chain,
        }
    )
    assert len(findings) == 1 and findings[0][0] == "INFO", "unknown must be INFO, never FAIL"


def test_a_gradient_in_an_unsupported_syntax_is_unknown_not_white():
    chain = [
        {
            "backgroundColor": "rgba(0, 0, 0, 0)",
            "backgroundImage": "linear-gradient(to right, lab(20% 5 5), lab(30% 5 5))",
        },
        {"backgroundColor": "rgb(255, 255, 255)", "backgroundImage": "none"},
    ]
    kind, _ = ua.resolve_effective_background(chain)
    assert kind == "unknown"


def test_transparent_is_a_known_answer_not_an_unknown_one():
    assert ua._is_unparseable_color("rgba(0, 0, 0, 0)") is False
    assert ua._is_unparseable_color("none") is False
    assert ua._is_unparseable_color("oklch(0.5 0.1 250)") is False
    assert ua._is_unparseable_color("lab(54% 81 70)") is True



SR_ONLY_INPUT = {
    "selector": "input#reorder-toggle-btn.sr-only.peer",
    "isControl": True,
    "text": "",
    "color": "rgb(250, 250, 250)",
    "clip": "rect(0px, 0px, 0px, 0px)",
    "clipPath": "none",
    "rectWidth": 1.0,
    "rectHeight": 1.0,
    "hasVisibleSibling": True,
    "bgChain": [{"backgroundColor": "rgb(248, 250, 252)", "backgroundImage": "none"}],
}

TEXTLESS_LABEL = {
    "selector": "label.relative.inline-flex",
    "isControl": True,
    "text": "",
    "color": "rgb(248, 250, 252)",
    "clip": "auto",
    "clipPath": "none",
    "rectWidth": 44.0,
    "rectHeight": 24.0,
    "hasVisibleSibling": True,
    "bgChain": [{"backgroundColor": "rgb(248, 250, 252)", "backgroundImage": "none"}],
}


def naive_invisible_control(element: dict) -> list:
    if not element.get("isControl"):
        return []
    fg = ua.parse_color(element.get("color", "") or "")
    if fg is None:
        return []
    kind, bg = ua.resolve_effective_background(element.get("bgChain") or [])
    if kind == "unknown":
        return []
    composited = ua.composite(fg, bg) if fg[3] < 0.999 else (fg[0], fg[1], fg[2])
    if ua.contrast_ratio(composited, bg) < ua.CONTRAST_AA_LARGE:
        return [("FAIL", "invisible-control", element.get("selector", "?"))]
    return []


def test_naive_judge_really_does_flag_the_sr_only_toggle_and_its_label():
    assert len(naive_invisible_control(SR_ONLY_INPUT)) == 1, "sr-only input should trip the naive judge"
    assert len(naive_invisible_control(TEXTLESS_LABEL)) == 1, "textless label should trip the naive judge"


def test_sr_only_toggle_with_a_visible_peer_is_not_flagged():
    assert ua.judge_invisible_control(SR_ONLY_INPUT) == []


def test_textless_control_is_not_judged_on_contrast():
    assert ua.judge_invisible_control(TEXTLESS_LABEL) == []


def test_the_exemption_does_not_blind_the_detector():
    stranded = dict(SR_ONLY_INPUT, hasVisibleSibling=False)
    findings = ua.judge_invisible_control(stranded)
    assert len(findings) == 1, "an sr-only control with nothing visible beside it must still fail"
    assert findings[0][1] == "invisible-control"
    assert "no visible affordance" in findings[0][2]


def test_sr_only_is_detected_by_mechanism_not_class_name():
    hand_rolled = dict(SR_ONLY_INPUT, selector="input#custom-toggle", clipPath="inset(50%)", clip="auto")
    assert ua.is_screen_reader_only(hand_rolled) is True

    liar = dict(SR_ONLY_INPUT, clip="auto", clipPath="none", rectWidth=120.0, rectHeight=40.0)
    assert ua.is_screen_reader_only(liar) is False, "a full-size element must not be exempted by name alone"



WASH = "linear-gradient(rgba(255, 251, 244, 0.55), rgba(255, 251, 244, 0) 360px)"


def test_wash_cover_flags_an_opaque_column_and_ignores_a_transparent_one():
    column = {"selector": "div.audit-trail", "backgroundColor": "rgb(250, 247, 242)", "backgroundImage": "none"}
    clear = {"selector": "div.page", "backgroundColor": "rgba(0, 0, 0, 0)", "backgroundImage": "none"}
    assert ua.judge_wash_cover(1440, WASH, [column])[0][:2] == ("WARN", "wash-cover")
    assert "div.audit-trail" in ua.judge_wash_cover(1440, WASH, [column])[0][2]
    assert ua.judge_wash_cover(1440, WASH, [clear])[0][0] == "PASS"


def test_wash_cover_needs_a_wash_to_hide_and_ignores_a_gradient_box():
    column = {"selector": "div.x", "backgroundColor": "rgb(250, 247, 242)", "backgroundImage": "none"}
    own_wash = {"selector": "div.y", "backgroundColor": "rgb(250, 247, 242)", "backgroundImage": WASH}
    assert ua.judge_wash_cover(1440, "none", [column]) == []
    assert ua.judge_wash_cover(1440, WASH, [own_wash])[0][0] == "PASS"


def test_row_overflow_flags_a_nowrap_row_but_not_a_scrolling_tab_strip():
    chips = {"selector": "div.chips", "flexWrap": "nowrap", "overflowX": "visible", "scrollWidth": 520, "clientWidth": 390}
    tabs = {"selector": "div.tabs", "flexWrap": "nowrap", "overflowX": "auto", "scrollWidth": 900, "clientWidth": 390}
    wraps = {"selector": "div.ok", "flexWrap": "wrap", "overflowX": "visible", "scrollWidth": 520, "clientWidth": 390}
    assert ua.judge_row_overflow(390, [chips])[0][:2] == ("WARN", "row-overflow")
    assert ua.judge_row_overflow(390, [tabs, wraps])[0][0] == "PASS"


def test_tap_targets_are_judged_on_a_phone_only_and_the_comfort_band_is_info():
    tiny = {"selector": "button.x", "width": 18, "height": 18}
    middling = {"selector": "button.y", "width": 36, "height": 36}
    assert ua.judge_tap_targets(1440, [tiny]) == []
    phone = ua.judge_tap_targets(390, [tiny, middling])
    assert [f[0] for f in phone] == ["WARN", "INFO"]
    assert ua.judge_tap_targets(390, [middling])[0][0] == "PASS"


def test_judge_page_runs_the_layout_judges():
    payload = {"layout": [{"width": 390, "bodyImage": WASH, "covers": [], "rows": [], "tapTargets": [{"selector": "a.z", "width": 10, "height": 10}]}]}
    assert any(code == "tap-target" and level == "WARN" for level, code, _ in ua.judge_page(payload))


def test_wash_cover_leaves_a_card_alone_but_flags_a_plain_column():
    plain = {"selector": "div.col", "backgroundColor": "rgb(250, 247, 242)", "backgroundImage": "none",
             "widthShare": 0.83, "borderRadius": "0px", "borderWidth": "0px", "boxShadow": "none"}
    card = dict(plain, selector="div.card", borderRadius="12px")
    bordered = dict(plain, selector="div.panel", borderWidth="1px")
    narrow = dict(plain, selector="div.side", widthShare=0.4)
    assert ua.judge_wash_cover(1440, WASH, [plain])[0][0] == "WARN"
    assert ua.judge_wash_cover(1440, WASH, [card, bordered, narrow])[0][0] == "PASS"
