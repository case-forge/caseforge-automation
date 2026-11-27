from __future__ import annotations

import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))

from vergil.goose import vergil_identity as gi


def test_product_name_is_vergil():
    assert gi.PRODUCT_NAME == "Vergil"


def test_strip_em_dashes_removes_the_character():
    assert "—" not in gi.strip_em_dashes("one thing—another thing")


def test_strip_em_dashes_preserves_ordinary_text():
    assert gi.strip_em_dashes("nothing to change here") == "nothing to change here"


def test_strip_em_dashes_replaces_with_a_readable_separator():
    result = gi.strip_em_dashes("first part—second part")
    assert result == "first part, second part"



def test_model_text_returns_stripped_text_on_success():
    result = types.SimpleNamespace(ok=True, text="  a real reply—with a dash  ")
    assert gi.model_text(result, fallback="fallback") == "a real reply, with a dash"


def test_model_text_returns_fallback_when_not_ok():
    result = types.SimpleNamespace(ok=False, text="")
    assert gi.model_text(result, fallback="fallback") == "fallback"


def test_model_text_returns_fallback_when_ok_but_empty():
    result = types.SimpleNamespace(ok=True, text="")
    assert gi.model_text(result, fallback="fallback") == "fallback"


def test_model_text_returns_fallback_when_ok_but_whitespace_only():
    result = types.SimpleNamespace(ok=True, text="   ")
    assert gi.model_text(result, fallback="fallback") == "fallback"
