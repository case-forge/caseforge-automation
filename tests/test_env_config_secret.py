from __future__ import annotations

import io
import json
import logging
import pickle
import pprint
import sys
import traceback
import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools"))

from env_config import Secret

VALUE = "sk-live-DO-NOT-LEAK-4f9a2c"


def test_str_and_repr_hide_the_value():
    s = Secret(VALUE)
    assert str(s) == "***"
    assert repr(s) == "<Secret ***>"
    assert VALUE not in str(s) + repr(s)


def test_every_string_interpolation_form_hides_the_value():
    s = Secret(VALUE)
    rendered = [
        f"{s}",
        f"{s!r}",
        f"{s!s}",
        "%s" % s,
        "%r" % s,
        "{}".format(s),
        "{!r}".format(s),
        format(s),
        str([s]),
        str({"token": s}),
        str((s,)),
    ]
    for text in rendered:
        assert VALUE not in text, f"value leaked through {text!r}"


def test_logging_does_not_render_the_value():
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("caseforge_env_secret_test")
    logger.handlers = [handler]
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    s = Secret(VALUE)
    logger.info("connecting with %s", s)
    logger.info("connecting with %r", s)
    logger.info(f"interpolated early: {s}")
    handler.flush()

    assert VALUE not in stream.getvalue()
    assert "***" in stream.getvalue()


def test_no_instance_dict_for_a_debugger_or_pprint_to_find():
    s = Secret(VALUE)
    assert not hasattr(s, "__dict__")
    try:
        vars(s)
    except TypeError:
        pass
    else:
        raise AssertionError("vars() succeeded, so the value is reachable by debug tools")
    assert VALUE not in pprint.pformat(s)
    assert VALUE not in pprint.pformat([s, {"k": s}])


def test_a_traceback_containing_the_secret_does_not_print_it():
    s = Secret(VALUE)

    def boom(token):
        raise RuntimeError(f"failed with {token}")

    try:
        boom(s)
    except RuntimeError:
        text = "".join(traceback.format_exception(*sys.exc_info()))
    assert VALUE not in text
    assert "***" in text


def test_it_is_not_json_serialisable_rather_than_serialising_the_value():
    try:
        json.dumps({"token": Secret(VALUE)})
    except TypeError:
        pass
    else:
        raise AssertionError("Secret was JSON-serialised; the value would reach the wire")


def test_reveal_is_the_only_way_out_and_returns_the_exact_value():
    s = Secret(VALUE)
    assert s.reveal() == VALUE
    assert s.reveal() is not None


def test_a_non_string_value_survives_unchanged():
    payload = {"user": "admin", "port": 1433}
    s = Secret(payload)
    assert s.reveal() is payload
    assert str(s) == "***"


def test_pickle_reaches_the_value_which_is_a_documented_limit():
    s = Secret(VALUE)
    assert VALUE.encode() in pickle.dumps(s), (
        "pickle no longer exposes the value -- if __reduce__ was added deliberately, "
        "invert this test and say so in env_config.py's comment block"
    )


def test_the_class_is_documented_as_not_being_encryption():
    source = (REPO_ROOT / "tools" / "env_config.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    documented = any(ast.get_docstring(node) for node in ast.walk(tree)
                     if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)))
    if not documented:
        pytest.skip("a published copy carries no docstrings; the source repository is where this is said")
    assert "not encryption" in source
