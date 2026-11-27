
from __future__ import annotations

import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
NOTICE = REPO_ROOT / "NOTICE"
REQUIREMENTS = REPO_ROOT / "requirements.txt"


def _normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _notice_names() -> set[str]:
    text = NOTICE.read_text(encoding="utf-8")
    return {_normalise(t) for t in re.findall(r"@?[A-Za-z0-9][\w.\-]*(?:/[\w.\-]+)?", text)}


def _python_requirements() -> list[str]:
    names = []
    for line in REQUIREMENTS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name = re.split(r"[<>=!~\[;\s]", line, maxsplit=1)[0].strip()
        if name:
            names.append(name)
    return names


def _npm_direct() -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for manifest in sorted(REPO_ROOT.glob("products/*/package.json")):
        data = json.loads(manifest.read_text(encoding="utf-8"))
        for section in ("dependencies", "devDependencies"):
            for name in data.get(section, {}):
                found.setdefault(name, []).append(manifest.parent.name)
    return found


def test_the_lists_are_not_empty():
    assert len(_python_requirements()) >= 20
    assert len(_npm_direct()) >= 20
    assert "requests" in {_normalise(n) for n in _python_requirements()}
    assert "next" in _npm_direct()


def test_every_python_requirement_is_in_notice():
    names = _notice_names()
    missing = sorted(n for n in _python_requirements() if _normalise(n) not in names)
    assert not missing, (
        f"requirements.txt declares {missing} but NOTICE has no entry for them. "
        f"Add each under its licence heading in NOTICE (AGENTS.md: 'Record every "
        f"licence in NOTICE'); read the licence from the installed metadata."
    )


def test_every_direct_npm_dependency_is_in_notice():
    names = _notice_names()
    missing = {
        n: where for n, where in sorted(_npm_direct().items()) if _normalise(n) not in names
    }
    assert not missing, (
        f"products/*/package.json declares {missing} but NOTICE has no entry for "
        f"them. Add each under its licence heading in NOTICE's NPM section."
    )


def test_a_missing_name_is_actually_detected():
    assert _normalise("definitely-not-a-real-dependency-xyz") not in _notice_names()
