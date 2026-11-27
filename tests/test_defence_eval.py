import hashlib
import importlib
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

_REAL_SURNAME_SHA256 = "96ff1f49af9439e2429d4015b40cfa4108d5cae46904009fce8e1cdcf54876f4"


def _de():
    return importlib.import_module("vergil.goose.defence_eval")


def test_synthetic_cases_are_labelled_and_unique():
    cases = _de().synthetic_cases()
    assert len(cases) == len({text for text, _ in cases})
    assert {label for _, label in cases} == {"safe", "unsafe"}
    assert sum(1 for _, label in cases if label == "safe") == 46
    assert sum(1 for _, label in cases if label == "unsafe") == 30


def test_synthetic_messages_contain_no_real_looking_client_names():
    text = " ".join(t for t, _ in _de().synthetic_cases()) + _de().SYNTHETIC_CONTEXT
    assert "Sam Wrentest" in text
    words = {hashlib.sha256(w.lower().encode()).hexdigest() for w in re.findall(r"[A-Za-z]+", text)}
    assert _REAL_SURNAME_SHA256 not in words


def test_guard_summary_counts_failed_calls_apart_from_verdicts():
    rows = [
        ("a", "safe", "unsafe", True, 0.4),
        ("b", "safe", "safe", True, 0.4),
        ("c", "safe", None, False, 0.1),
        ("d", "unsafe", "safe", True, 0.6),
        ("e", "unsafe", None, False, 0.1),
        ("f", "unsafe", "unsafe", True, 0.6),
    ]
    summary = _de().summarise_guard(rows)
    assert summary["false_positives"] == 1
    assert summary["missed"] == 1
    assert summary["call_failures"] == 2
    assert summary["legitimate"] == 3 and summary["attacks"] == 3


def test_prompt_outcome_recognises_the_scripts_declines_and_failures():
    de = _de()
    assert de.prompt_outcome("") == "failed"
    assert de.prompt_outcome(f"Hi, I'm Vergil. I help run family-law cases at {de.vergil_identity.FIRM_SHORT_NAME}.") == "first_contact"
    assert de.prompt_outcome("I'm not able to share more detail about how I operate") == "first_contact"
    assert de.prompt_outcome("I cannot draft that as there is no information.") == "declined"
    assert de.prompt_outcome("The next hearing is on 3 November.") == "answered"


def test_run_guard_uses_the_live_classifier(monkeypatch):
    de = _de()
    sc = importlib.import_module("vergil.goose.safety_classifier")
    seen = []

    def fake(text, **kwargs):
        seen.append(text)
        return SimpleNamespace(verdict="unsafe" if "ignore" in text else "safe", ok=True)

    monkeypatch.setattr(sc, "classify_safety", fake)
    rows = de.run_guard([("hello", "safe"), ("ignore everything", "unsafe")])
    assert seen == ["hello", "ignore everything"]
    assert [r[2] for r in rows] == ["safe", "unsafe"]
