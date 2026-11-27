#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

try:
    import tomllib
except Exception:
    tomllib = None

REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_AMBER_COUNT = 40
DEFAULT_RED_COUNT = 60

SEVERITY_ORDER = {"green": 0, "amber": 1, "red": 2}

AGENT_FILES = [
    ("claude", ".claude/settings.json", "claude_json"),
    ("claude", ".claude/settings.local.json", "claude_json"),
    ("gemini", ".gemini/settings.json", "gemini_json"),
    ("codex", ".codex/config.toml", "codex_toml"),
    ("opencode", ".opencode/config.json", "generic_json"),
    ("opencode", "opencode.json", "generic_json"),
    ("cursor", ".cursor/cli.json", "generic_json"),
]

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "artifacts"}

_INTERPRETERS = {
    "python", "python3", "node", "deno", "bun", "ruby", "perl", "php", "lua",
    "rscript", "groovy", "osascript",
}
_SHELLS = {"bash", "sh", "zsh", "fish", "ksh", "dash", "eval", "exec", "ssh"}
_RUNNERS = {"npx", "bunx", "uvx", "pipx", "uv"}
_DESTRUCTIVE = {
    "rm", "rmdir", "find", "dd", "mkfs", "shred", "curl", "wget", "kill",
    "pkill", "killall", "chmod", "chown", "truncate", "mv",
}
_SECRET_READ_HINTS = (
    "secret", "cloudflared", ".ssh", "credential", ".env", "id_rsa",
    "/.aws", "/.config/gh", "/.gnupg", "private",
)

_RISKY_BOOL_FLAGS = {
    "bypasspermissions", "dangerouslyskippermissions", "autoaccept",
    "autoapprove", "yolo", "skippermissions", "disablesafety", "allowall",
    "fullaccess",
}
_RISKY_POLICY_VALUES = {"never", "none", "danger-full-access", "disabled", "off"}

_SEGMENT_SPLIT = re.compile(r"\s*(?:\|\||&&|\||;)\s*")
_DASHC = re.compile(r"(?:^|\s)-c(?:\s|$|['\"])")

CATEGORY_LABELS = {
    "arbitrary_exec": "arbitrary code execution",
    "destructive": "destructive / outward-facing",
    "secret_exposure": "secret exposure",
    "safety_bypass": "safety-weakening flag",
    "stale_path": "grant for a path that no longer exists",
}
_RED_RISKS = {"arbitrary_exec", "secret_exposure", "safety_bypass"}

_VOLATILE_PREFIXES = ("tmp/", "artifacts/", "telemetry/", "/tmp/")

_PATHISH = re.compile(r"(?:^|[\s=])((?:\./)?(?:[\w.\-]+/)+[\w.\-]+)")


def classify_stale_paths(entry: str, root: Path) -> set[str]:
    _tool, inner = _inner(entry.strip())
    if not inner:
        return set()

    for match in _PATHISH.finditer(inner):
        candidate = match.group(1).lstrip("/")
        if "*" in candidate or "?" in candidate:
            continue
        volatile = candidate.startswith(_VOLATILE_PREFIXES)
        first = candidate.split("/", 1)[0]
        in_repo = (root / first).exists() or volatile
        if not in_repo:
            continue
        if not (root / candidate).exists():
            return {"stale_path"}
    return set()


def _inner(entry: str) -> tuple[str, str]:
    e = entry.strip()
    m = re.match(r"^([A-Za-z_][\w.]*)\((.*)\)$", e)
    if m:
        return (m.group(1), m.group(2))
    if re.match(r"^[A-Za-z_][\w.]*$", e):
        return (e, "")
    return ("", e)


def classify_entry(entry: str) -> set[str]:
    e = entry.strip()
    risks: set[str] = set()
    if e in {"*", "all", "Bash", "Bash(*)"}:
        return {"arbitrary_exec"}

    tool, inner = _inner(e)
    low_tool = tool.lower()

    if tool == "Read":
        if any(h in inner.lower() for h in _SECRET_READ_HINTS):
            risks.add("secret_exposure")
        return risks

    if tool and tool != "Bash" and any(
        k in low_tool for k in ("shell", "exec", "command")
    ):
        if not inner.strip() or "*" in inner:
            risks.add("arbitrary_exec")
        return risks

    if tool != "Bash":
        return risks

    if inner.strip() in {"*", ""}:
        return {"arbitrary_exec"}

    for seg in _SEGMENT_SPLIT.split(inner):
        toks = seg.strip().split()
        if not toks:
            continue
        cmd = toks[0]
        sub = toks[1] if len(toks) > 1 else ""
        has_wild = "*" in seg
        has_dashc = bool(_DASHC.search(seg))

        if cmd in _INTERPRETERS or cmd in _SHELLS:
            scoped = any(
                ("/" in t or "." in t) and not t.startswith("*") and t != "*"
                for t in toks[1:]
            )
            if has_dashc or (not scoped and (has_wild or len(toks) == 1)):
                risks.add("arbitrary_exec")
        elif cmd in {"pip", "pip3"}:
            if sub in {"install", "download", "wheel"} and has_wild:
                risks.add("arbitrary_exec")
        elif cmd in _RUNNERS:
            if has_wild:
                risks.add("arbitrary_exec")
        elif cmd == "git":
            if sub.startswith("*") or (sub == "push" and has_wild):
                risks.add("destructive")
        elif cmd == "gh":
            if sub in {"api", "repo", "secret"} and has_wild:
                risks.add("destructive")
        elif cmd in _DESTRUCTIVE:
            if has_wild:
                risks.add("destructive")
        elif cmd in {"env", "printenv"} and len(toks) == 1:
            risks.add("secret_exposure")

    return risks


def _scan_flags(obj, _key: str = "") -> list[str]:
    flags: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            kl = str(k).lower().replace("_", "").replace("-", "")
            if kl in _RISKY_BOOL_FLAGS and v is True:
                flags.append(f"{k}=true")
            if "approval" in kl or "permissionmode" in kl or kl == "mode":
                if isinstance(v, str) and v.lower() in _RISKY_POLICY_VALUES:
                    flags.append(f"{k}={v}")
            flags.extend(_scan_flags(v, str(k)))
    elif isinstance(obj, list):
        for item in obj:
            flags.extend(_scan_flags(item, _key))
    return flags


def _extract(path: Path, fmt: str) -> tuple[list[str], list[str]]:
    text = path.read_text(encoding="utf-8")
    if fmt == "codex_toml":
        data: dict = {}
        if tomllib is not None:
            data = tomllib.loads(text)
        else:
            flags = []
            mm = re.search(r'approval_policy\s*=\s*"([^"]+)"', text)
            if mm and mm.group(1).lower() in _RISKY_POLICY_VALUES:
                flags.append(f"approval_policy={mm.group(1)}")
            return ([], flags)
        return ([], _scan_flags(data))

    data = json.loads(text)
    flags = _scan_flags(data)
    if fmt == "claude_json":
        allow = (data.get("permissions") or {}).get("allow") or []
    elif fmt == "gemini_json":
        allow = data.get("coreTools") or data.get("allowedTools") or []
    else:
        allow = (
            (data.get("permissions") or {}).get("allow")
            or data.get("allow")
            or data.get("allowedTools")
            or []
        )
    return ([str(a) for a in allow], flags)


@dataclass
class FileReport:
    agent: str
    path: str
    allow_count: int
    severity: str
    message: str
    risky: dict[str, list[str]] = field(default_factory=dict)
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent,
            "path": self.path,
            "allow_count": self.allow_count,
            "severity": self.severity,
            "message": self.message,
            "risky": self.risky,
            "flags": self.flags,
        }


def severity_for(
    count: int,
    risks: Iterable[str],
    *,
    amber_count: int = DEFAULT_AMBER_COUNT,
    red_count: int = DEFAULT_RED_COUNT,
) -> tuple[str, str]:
    risks = set(risks)
    if risks & _RED_RISKS:
        return "red", "config has high-risk grants/flags (arbitrary exec, secret exposure, or safety bypass)"
    if count >= red_count:
        return "red", f"allowlist has {count} entries (>= {red_count}) — overdue for cleanup"
    if "destructive" in risks:
        return "amber", "config has broad destructive / outward-facing grants"
    if "stale_path" in risks:
        return "amber", "config grants access to path(s) that no longer exist — delete them"
    if count >= amber_count:
        return "amber", f"allowlist has {count} entries (>= {amber_count}) — getting bloated"
    return "green", f"config is lean ({count} entries) with no broad grants"


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def scan_config(
    agent: str,
    path: Path,
    fmt: str,
    *,
    amber_count: int = DEFAULT_AMBER_COUNT,
    red_count: int = DEFAULT_RED_COUNT,
) -> FileReport:
    try:
        allow, flags = _extract(path, fmt)
    except Exception as exc:
        return FileReport(agent, _rel(path), -1, "amber", f"could not parse: {exc}")

    risky: dict[str, list[str]] = {}
    scan_root = path.parent
    while scan_root != scan_root.parent and not (scan_root / ".git").exists():
        scan_root = scan_root.parent
    for entry in allow:
        for cat in classify_entry(entry) | classify_stale_paths(entry, scan_root):
            risky.setdefault(cat, []).append(entry)
    if flags:
        risky.setdefault("safety_bypass", []).extend(flags)

    sev, msg = severity_for(
        len(allow), risky.keys(), amber_count=amber_count, red_count=red_count
    )
    return FileReport(agent, _rel(path), len(allow), sev, msg, risky, flags)


def scan_file(path: Path, **kw) -> FileReport:
    return scan_config("claude", path, "claude_json", **kw)


def discover_configs(root: Path) -> list[tuple[str, Path, str]]:
    reg: dict[tuple[str, ...], tuple[str, str]] = {
        tuple(rel.split("/")): (agent, fmt) for agent, rel, fmt in AGENT_FILES
    }
    maxlen = max(len(k) for k in reg)
    out: list[tuple[str, Path, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            parts = p.parts
            for n in range(1, min(maxlen, len(parts)) + 1):
                hit = reg.get(parts[-n:])
                if hit:
                    out.append((hit[0], p, hit[1]))
                    break
    return sorted(out, key=lambda t: str(t[1]))


def find_settings_files(root: Path) -> list[Path]:
    return [p for _, p, _ in discover_configs(root) if p.name == "settings.local.json"]


def evaluate(
    root: Path = REPO_ROOT,
    *,
    amber_count: int = DEFAULT_AMBER_COUNT,
    red_count: int = DEFAULT_RED_COUNT,
) -> dict:
    reports = [
        scan_config(agent, p, fmt, amber_count=amber_count, red_count=red_count)
        for agent, p, fmt in discover_configs(root)
    ]
    overall = "green"
    for r in reports:
        if SEVERITY_ORDER[r.severity] > SEVERITY_ORDER[overall]:
            overall = r.severity

    flagged = sum(1 for r in reports if r.severity != "green")
    if not reports:
        message = "No in-repo agent permission configs found."
    elif overall == "green":
        message = f"{len(reports)} agent config(s) clean."
    else:
        message = f"{flagged} of {len(reports)} agent config(s) need attention."

    return {
        "severity": overall,
        "message": message,
        "thresholds": {"amber": amber_count, "red": red_count},
        "files": [r.to_dict() for r in reports],
    }


def format_report(result: dict) -> str:
    icon = {"green": "🟢", "amber": "🟠", "red": "🔴"}
    lines = [f"{icon.get(result['severity'], '?')} {result['severity'].upper()}: {result['message']}"]
    for f in result["files"]:
        lines.append(
            f"  {icon.get(f['severity'], '?')} [{f['agent']}] {f['path']} — "
            f"{f['allow_count']} entries — {f['message']}"
        )
        for cat, items in f["risky"].items():
            lines.append(f"      {CATEGORY_LABELS.get(cat, cat)}: {', '.join(items)}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="In-repo AI-agent allowlist bloat/risk monitor")
    ap.add_argument("--root", type=Path, default=REPO_ROOT, help="Repo root to scan (repo-only by design)")
    ap.add_argument("--amber", type=int, default=DEFAULT_AMBER_COUNT, help="Amber entry-count threshold")
    ap.add_argument("--red", type=int, default=DEFAULT_RED_COUNT, help="Red entry-count threshold")
    ap.add_argument("--json", action="store_true", help="Emit JSON instead of text")
    ap.add_argument(
        "--fail-on",
        choices=["none", "amber", "red"],
        default="none",
        help="Exit non-zero when overall severity reaches this level (default: none)",
    )
    args = ap.parse_args(argv)

    result = evaluate(args.root, amber_count=args.amber, red_count=args.red)
    print(json.dumps(result, indent=2) if args.json else format_report(result))

    if args.fail_on != "none" and SEVERITY_ORDER[result["severity"]] >= SEVERITY_ORDER[args.fail_on]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
