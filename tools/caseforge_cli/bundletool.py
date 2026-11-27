from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any, Callable

from caseforge_cli.base import check_version, resolve_repo, run_cli_json

PINNED_VERSION = "1.6.0"

_ENV_VAR = "BUNDLETOOL_REPO_PATH"
_MERGED_RELPATH = "bundletool"
_STANDALONE_DIRNAME = "bundletool"
_ENTRY_RELPATH = "scripts/build-cli.mjs"


class BundleToolCLI:

    def __init__(self, repo_path: str | Path | None = None, *, expected_version: str | None = PINNED_VERSION):
        self.repo = Path(repo_path).expanduser() if repo_path else resolve_repo(
            env_var=_ENV_VAR,
            merged_relpath=_MERGED_RELPATH,
            standalone_dirname=_STANDALONE_DIRNAME,
            entry_relpath=_ENTRY_RELPATH,
        )
        self._entry = self.repo / _ENTRY_RELPATH
        self.version = check_version([str(self._entry)], tool="bundletool", cwd=self.repo, expected=expected_version)

    def render(
        self,
        manifest: dict[str, Any] | str | Path,
        docs_dir: str | Path,
        output_path: str | Path,
        *,
        force: bool = False,
        timeout: float = 300.0,
        preexec_fn: Callable[[], None] | None = None,
    ) -> dict[str, Any]:
        if isinstance(manifest, dict):
            with tempfile.NamedTemporaryFile(
                "w", suffix=".json", prefix="bundletool-manifest-", delete=False, encoding="utf-8"
            ) as fh:
                json.dump(manifest, fh)
                manifest_path = Path(fh.name)
        else:
            manifest_path = Path(manifest).expanduser()

        argv = [str(self._entry), "--json"]
        if force:
            argv.append("--force")
        argv.extend([str(manifest_path), str(Path(docs_dir).expanduser()), str(Path(output_path).expanduser())])
        return run_cli_json(argv, tool="bundletool", cwd=self.repo, timeout=timeout, preexec_fn=preexec_fn)

    def config_keys(self) -> str:
        import subprocess

        from caseforge_cli.base import node_bin

        proc = subprocess.run(
            [node_bin(), str(self._entry), "--config-keys"],
            capture_output=True,
            text=True,
            timeout=15,
            cwd=str(self.repo),
        )
        return proc.stdout
