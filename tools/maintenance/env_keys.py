#!/usr/bin/env python3
"Show what is inside a .env-style secrets file without ever printing a"
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from env_bootstrap import parse_env_file


def _shape(value: str) -> str:
    "A length + character-class summary, never the value itself."
    if not value:
        return "empty"
    classes = []
    if any(c.isalpha() for c in value):
        classes.append("alpha")
    if any(c.isdigit() for c in value):
        classes.append("digit")
    if any(not c.isalnum() for c in value):
        classes.append("symbol")
    return f"{len(value)} chars, {'+'.join(classes) or 'none'}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="path to a .env-style file")
    ap.add_argument("--check", metavar="KEY", help="report only whether one key is set (still no value)")
    ap.add_argument("--diff-keys", metavar="OTHER_PATH", help="show keys present in one file but not the other")
    args = ap.parse_args()

    path = Path(args.path)
    if not path.is_file():
        print(f"[refuse] {path} does not exist or is not a file", file=sys.stderr)
        return 1

    env = parse_env_file(path)

    if args.diff_keys:
        other = parse_env_file(Path(args.diff_keys))
        only_here = sorted(set(env) - set(other))
        only_there = sorted(set(other) - set(env))
        print(f"only in {path}: {only_here or '(none)'}")
        print(f"only in {args.diff_keys}: {only_there or '(none)'}")
        return 0

    if args.check:
        if args.check in env:
            print(f"{args.check}: set ({_shape(env[args.check])})")
            return 0
        print(f"{args.check}: NOT SET")
        return 1

    if not env:
        print(f"{path}: no KEY=value lines found")
        return 0
    width = max(len(k) for k in env)
    for key in sorted(env):
        print(f"{key.ljust(width)}  {_shape(env[key])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
