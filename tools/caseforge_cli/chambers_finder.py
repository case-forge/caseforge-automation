from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Literal

from caseforge_cli.base import resolve_repo, check_version, run_cli_json

PINNED_VERSION = "1.0.0"

_ENV_VAR = "CHAMBERS_FINDER_REPO_PATH"
_MERGED_RELPATH = "chambers-finder-cli"
_STANDALONE_DIRNAME = "chambers-finder"
_ENTRY_RELPATH = "cli.mjs"

DATA_ENV_VAR = "CHAMBERS_FINDER_DATA_PATH"
_DATA_RELPATHS = ("../static/finder-data.json", "../chambers-finder/static/finder-data.json")


def _cli_repo() -> Path:
    return resolve_repo(
        env_var=_ENV_VAR,
        merged_relpath=_MERGED_RELPATH,
        standalone_dirname=_STANDALONE_DIRNAME,
        entry_relpath=_ENTRY_RELPATH,
    )


def finder_data_path(repo_path: str | Path | None = None) -> Path:
    override = os.environ.get(DATA_ENV_VAR, "").strip()
    if override:
        return Path(override).expanduser()
    repo = Path(repo_path).expanduser() if repo_path else _cli_repo()
    candidates = [(repo / rel).resolve() for rel in _DATA_RELPATHS]
    return next((path for path in candidates if path.is_file()), candidates[0])


def load_finder_data(repo_path: str | Path | None = None) -> dict[str, Any] | None:
    try:
        payload = json.loads(finder_data_path(repo_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


class ChambersFinderCLI:
    def __init__(self, repo_path: str | Path | None = None, *, expected_version: str | None = PINNED_VERSION):
        self.repo = Path(repo_path).expanduser() if repo_path else _cli_repo()
        self._entry = self.repo / _ENTRY_RELPATH
        self.version = check_version(
            [str(self._entry)], tool="chambers-finder-cli", cwd=self.repo, expected=expected_version
        )

    def nearest(
        self,
        postcode: str,
        *,
        courts: int = 3,
        chambers: int = 5,
        radius_miles: float | Literal["all"] | None = None,
        court_id: str | None = None,
        measure_from: Literal["court", "postcode"] = "court",
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        argv = [str(self._entry), "--json", "--postcode", postcode, "--courts", str(courts), "--chambers", str(chambers)]
        if radius_miles is not None:
            argv.extend(["--radius-miles", str(radius_miles)])
        if court_id:
            argv.extend(["--court-id", court_id])
        if measure_from != "court":
            argv.extend(["--measure-from", measure_from])
        return run_cli_json(argv, tool="chambers-finder-cli", cwd=self.repo, timeout=timeout)
