#!/usr/bin/env python3
"""Configure GitHub branch protection for gotouhou repositories.

Requires `gh auth login` with repository administration permissions.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass


ORG = "Phantasm-Klash"


@dataclass(frozen=True)
class RepoProtection:
    repo: str
    checks: tuple[str, ...]


REPOSITORIES = (
    RepoProtection("docs", ("docs-audit",)),
    RepoProtection("SpellKard", ("client-static-audit",)),
    RepoProtection("Gensoulkyo", ("server-contract-tests",)),
    RepoProtection("PhK-Protocol", ("protocol-checks",)),
    RepoProtection("PhK-BattleServer", ("battle-server-checks",)),
)


def gh(*args: str, input_text: str | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=check,
    )


def api_json(method: str, path: str, payload: dict[str, object] | None = None, check: bool = True) -> dict[str, object]:
    args = ["api", "--method", method, path]
    input_text = None
    if payload is not None:
        args.extend(["--input", "-"])
        input_text = json.dumps(payload)
    completed = gh(*args, input_text=input_text, check=check)
    if not completed.stdout.strip():
        return {}
    return json.loads(completed.stdout)


def configure_repo(repo_config: RepoProtection) -> None:
    repo = repo_config.repo
    api_json("PATCH", f"/repos/{ORG}/{repo}", {"delete_branch_on_merge": True})
    protection = {
        "required_status_checks": {
            "strict": True,
            "contexts": list(repo_config.checks),
        },
        "enforce_admins": False,
        "required_pull_request_reviews": {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": 1,
            "require_last_push_approval": False,
        },
        "restrictions": None,
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": True,
    }
    api_json("PUT", f"/repos/{ORG}/{repo}/branches/main/protection", protection)
    print(f"{repo}: protected main with checks={','.join(repo_config.checks)}")


def main() -> int:
    for repo in REPOSITORIES:
        configure_repo(repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
