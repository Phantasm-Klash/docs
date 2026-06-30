#!/usr/bin/env python3
"""Lightweight invariants for goal agent manager summary shaping."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path


OPS_DIR = Path(__file__).resolve().parent
if str(OPS_DIR) not in sys.path:
    sys.path.insert(0, str(OPS_DIR))

import goal_agent_manager  # noqa: E402
import hourly_progress_mail  # noqa: E402


def check_legacy_resource_risk_is_structured_not_managed() -> None:
    summary = goal_agent_manager.build_agent_resource_risk(
        {
            "client-agent": {
                "repo": "SpellKard",
                "status": "running",
                "runtime_log": {"token_usage": goal_agent_manager.TOKEN_HIGH_RISK, "bytes": 1200},
            },
            "audit-agent": {
                "repo": "docs",
                "status": "running",
                "runtime_log": {"token_usage": 1000, "bytes": 1200},
            },
        },
        {
            "old_roster_records": ["legacy-client"],
            "legacy_log_prefixes": [{"prefix": "legacy-client"}],
        },
    )

    assert summary["high_count"] == 1
    assert summary["medium_count"] == 0
    assert summary["legacy_count"] == 1
    assert summary["legacy_items"][0]["agent"] == "legacy-agent-roster"
    assert any(item["agent"] == "legacy-agent-roster" for item in summary["items"])
    assert all(item["agent"] != "legacy-agent-roster" for item in summary["top_items"])

    mail_lines = hourly_progress_mail.agent_resource_risk_lines({"agent_resource_risk": summary})
    assert "legacy=1" in mail_lines[0]
    assert not any("legacy-agent-roster" in line for line in mail_lines[1:])


def check_pending_pr_checks_are_not_reported_as_branch_gate() -> None:
    priority, category, action = goal_agent_manager.classify_pull_request_action(
        {"mergeStateStatus": "BLOCKED"},
        {"pending": 1, "failed": 0},
    )

    assert priority == 30
    assert category == "wait_checks"
    assert action == "wait for pending checks"

    priority, category, action = goal_agent_manager.classify_pull_request_action(
        {"mergeStateStatus": "BLOCKED"},
        {"pending": 0, "failed": 0},
    )

    assert priority == 40
    assert category == "blocked_gate"
    assert action == "wait for required review/check gates or branch protection"


def check_dirty_repo_owner_prefers_active_workdir_agent() -> None:
    repo_path = str(Path("/tmp/gotouhou-docs-root").resolve())
    summary = goal_agent_manager.build_repo_state_risk(
        {
            "docs": {
                "repo": "docs",
                "path": repo_path,
                "branch": "main",
                "head": "abc123",
                "status": "## main...origin/main\n M ops/goal_agent_manager.py",
                "dirty_count": 1,
                "dirty": [" M ops/goal_agent_manager.py"],
            }
        },
        {
            "audit-agent": {
                "repo": "docs",
                "status": "running",
                "workdir": repo_path,
            },
            "project-manager-agent": {
                "repo": "docs",
                "status": "running",
                "workdir": str(Path("/tmp/gotouhou-pm-docs").resolve()),
            },
        },
    )

    assert summary["count"] == 1
    assert summary["items"][0]["category"] == "dirty_worktree"
    assert summary["items"][0]["owner_agent"] == "audit-agent"
    assert summary["by_owner_agent"] == {"audit-agent": 1}


def check_mail_summary_falls_back_when_primary_is_invalid() -> None:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        primary = tmp / "goal-agent-summary.json"
        fallback = tmp / "last-watchdog-summary.json"
        primary.write_text("{bad json", encoding="utf-8")
        fallback.write_text(
            """
{
  "generated_at": "2026-06-30T12:00:00Z",
  "agents": {
    "client-agent": {"status": "running", "repo": "SpellKard"}
  },
  "regression": {"ok": true, "failed_count": 0},
  "pull_request_queue": {"open_count": 0, "needs_action_count": 0, "ready_count": 0}
}
""".strip()
            + "\n",
            encoding="utf-8",
        )

        original_fallback = hourly_progress_mail.LEGACY_WATCHDOG_SUMMARY
        try:
            hourly_progress_mail.LEGACY_WATCHDOG_SUMMARY = str(fallback)
            selected, summary = hourly_progress_mail.load_summary_with_fallback(primary)
        finally:
            hourly_progress_mail.LEGACY_WATCHDOG_SUMMARY = original_fallback

    assert selected == fallback
    assert summary["generated_at"] == "2026-06-30T12:00:00Z"
    assert "client-agent" in summary["agents"]


def main() -> int:
    check_legacy_resource_risk_is_structured_not_managed()
    check_pending_pr_checks_are_not_reported_as_branch_gate()
    check_dirty_repo_owner_prefers_active_workdir_agent()
    check_mail_summary_falls_back_when_primary_is_invalid()
    print("check_goal_agent_manager ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
