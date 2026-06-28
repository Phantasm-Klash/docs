#!/usr/bin/env python3
"""Run local cross-repository protocol and network contract checks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


CHECKS = (
    ("PhK-Protocol", ["python3", "tools/check_protocol.py"]),
    ("Gensoulkyo", ["go", "test", "./runtime/...", "./cmd/gensoulkyo_nakama"]),
    ("PhK-BattleServer", ["python3", "tools/check_battle_server.py"]),
)


def run(root: Path, repo: str, command: list[str]) -> int:
    cwd = root / repo
    print(f"## {repo}: {' '.join(command)}", flush=True)
    if not cwd.exists():
        print(f"missing repository path: {cwd}", file=sys.stderr)
        return 1
    completed = subprocess.run(command, cwd=str(cwd), text=True)
    print("", flush=True)
    return completed.returncode


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/root/gotouhou")
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()

    failures = 0
    for repo, command in CHECKS:
        if run(root, repo, command) != 0:
            failures += 1
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
