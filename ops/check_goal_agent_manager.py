#!/usr/bin/env python3
"""Lightweight invariants for goal agent manager summary shaping."""

from __future__ import annotations

import sys
import tempfile
import os
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


def check_agent_health_promotes_version_and_resource_risk() -> None:
    agents = {
        "client-agent": {
            "repo": "SpellKard",
            "status": "running",
            "progress": True,
            "key_available": True,
            "worktree_state": {"missing": False, "dirty_count": 0, "ahead": 6, "behind": 0},
        },
        "battle-server-agent": {
            "repo": "PhK-BattleServer",
            "status": "running",
            "progress": True,
            "key_available": True,
            "worktree_state": {"missing": False, "dirty_count": 0, "ahead": 0, "behind": 0},
        },
        "nakama-server-agent": {
            "repo": "Gensoulkyo",
            "status": "running",
            "progress": True,
            "key_available": True,
            "worktree_state": {"missing": False, "dirty_count": 0, "ahead": 0, "behind": 0},
        },
        "audit-agent": {
            "repo": "docs",
            "status": "running",
            "progress": True,
            "key_available": True,
            "worktree_state": {"missing": False, "dirty_count": 0, "ahead": 0, "behind": 0},
        },
        "project-manager-agent": {
            "repo": "docs",
            "status": "running",
            "progress": True,
            "key_available": True,
            "worktree_state": {"missing": False, "dirty_count": 0, "ahead": 0, "behind": 0},
        },
    }
    repo_state_risk = {
        "items": [
            {
                "owner_agent": "client-agent",
                "repo": "SpellKard",
                "priority": 16,
                "category": "local_ahead",
                "action": "push or convert the local commits into a current-base PR",
            }
        ]
    }
    pull_request_queue = {"items": []}
    resource_risk = {
        "items": [
            {
                "agent": "client-agent",
                "repo": "SpellKard",
                "severity": "high",
                "action": "split next work into a smaller PR-ready slice",
            }
        ]
    }
    next_actions = {
        "items": [
            {
                "agent": "client-agent",
                "action": "push or convert the local commits into a current-base PR",
            }
        ]
    }

    health = goal_agent_manager.build_agent_health(
        agents,
        repo_state_risk,
        pull_request_queue,
        resource_risk,
        next_actions,
    )

    assert health["score"] == health["average_score"]
    assert health["label"] == goal_agent_manager.health_label(health["average_score"])
    assert health["agents"]["client-agent"]["score"] < health["agents"]["battle-server-agent"]["score"]
    assert "client-agent" in health["low_score_agents"]
    assert any("资源风险 high" in reason for reason in health["agents"]["client-agent"]["reasons"])
    assert any("agent worktree ahead=6" in reason for reason in health["agents"]["client-agent"]["reasons"])
    mail_lines = hourly_progress_mail.agent_health_lines({"agent_health": health})
    assert any("client-agent" in line and "score=" in line for line in mail_lines)


def check_read_only_samples_do_not_persist_authoritative_state() -> None:
    with tempfile.TemporaryDirectory(prefix="goal-agent-manager-check-") as tmp:
        root = Path(tmp)
        key_file = root / "keys"
        key_file.write_text("other: dummy-local-test-key\n", encoding="utf-8")

        original_collect_repo = goal_agent_manager.collect_repo
        original_collect_pull_requests = goal_agent_manager.collect_pull_requests
        original_collect_runtime = goal_agent_manager.collect_runtime
        original_collect_legacy_agents = goal_agent_manager.collect_legacy_agents
        original_prepare_worktree = goal_agent_manager.prepare_worktree
        try:
            goal_agent_manager.collect_repo = lambda root, name: {
                "repo": name,
                "path": str(root / name),
                "branch": "main",
                "head": "0000000",
                "status": "## main...origin/main",
                "dirty_count": 0,
                "dirty": [],
                "commits_last_interval": [],
            }
            goal_agent_manager.collect_pull_requests = lambda root, now: {
                name: {
                    "repo": name,
                    "open_count": 0,
                    "items": [],
                    "status": 0,
                    "collected_at": goal_agent_manager.iso(now),
                    "error": "",
                }
                for name in goal_agent_manager.DEFAULT_REPOS
            }
            goal_agent_manager.collect_runtime = lambda root: {
                "godot_linux": {"exists": False, "executable": False},
                "docker": {"available": False, "docker_compose_available": False},
            }
            goal_agent_manager.collect_legacy_agents = lambda root: {
                "old_roster_records": [],
                "legacy_log_prefixes": [],
            }
            goal_agent_manager.prepare_worktree = lambda root, agent_id, agent, dry_run: {
                "path": str(root / agent["repo"]),
                "ready": True,
                "repo": agent["repo"],
                "branch": agent.get("branch") or "main",
                "test_stub": True,
                "dry_run": bool(dry_run),
            }

            for flag in ("--dry-run", "--no-start"):
                summary = goal_agent_manager.build_summary(
                    goal_agent_manager.parse_args(["--root", str(root), "--key-file", str(key_file), flag])
                )

                assert summary["read_only_sample"] is True
                assert summary["started_count"] == 0
                assert not (root / ".agents" / "goal-agent-summary.json").exists()
                assert not (root / ".agents" / "last-watchdog-summary.json").exists()
                assert not (root / ".agents" / "reports" / "audit-agent-latest.md").exists()
                assert not (root / ".agents" / "reports" / "plan-audit-latest.md").exists()
        finally:
            goal_agent_manager.collect_repo = original_collect_repo
            goal_agent_manager.collect_pull_requests = original_collect_pull_requests
            goal_agent_manager.collect_runtime = original_collect_runtime
            goal_agent_manager.collect_legacy_agents = original_collect_legacy_agents
            goal_agent_manager.prepare_worktree = original_prepare_worktree


def check_live_lock_log_is_preferred_over_latest_old_log() -> None:
    with tempfile.TemporaryDirectory(prefix="goal-agent-manager-log-") as tmp:
        root = Path(tmp)
        log_dir = root / ".agents" / "logs"
        log_dir.mkdir(parents=True)
        old_log = log_dir / "project-manager-agent-20260630T150000Z.log"
        live_log = log_dir / "project-manager-agent-20260630T151500Z.log"
        old_log.write_text("[goal-manager] exited status=0\ntokens used\n999,999\n", encoding="utf-8")
        live_log.write_text("[goal-manager] started project-manager-agent\n", encoding="utf-8")
        os.utime(old_log, (1, 1))
        os.utime(live_log, (2, 2))

        selected = goal_agent_manager.current_log_path(
            root,
            "project-manager-agent",
            {"alive": True, "log_path": str(live_log)},
        )
        assert selected == live_log
        live_info = goal_agent_manager.log_info(selected)
        assert live_info["exists"] is True
        assert live_info["exit_status"] is None
        assert live_info["token_usage"] is None

        selected_after_exit = goal_agent_manager.current_log_path(
            root,
            "project-manager-agent",
            {"alive": False, "log_path": str(live_log)},
        )
        assert selected_after_exit == live_log


def check_exit_status_only_uses_runner_marker_line() -> None:
    with tempfile.TemporaryDirectory(prefix="goal-agent-manager-exit-") as tmp:
        root = Path(tmp)
        log_path = root / "project-manager-agent-20260630T160000Z.log"
        log_path.write_text(
            "diff context mentions [goal-manager] exited status=1 inside a line\n"
            " normal output\n"
            "[goal-manager] exited status=0\n",
            encoding="utf-8",
        )
        info = goal_agent_manager.log_info(log_path)
        assert info["exit_status"] == 0


def main() -> int:
    check_legacy_resource_risk_is_structured_not_managed()
    check_agent_health_promotes_version_and_resource_risk()
    check_read_only_samples_do_not_persist_authoritative_state()
    check_live_lock_log_is_preferred_over_latest_old_log()
    check_exit_status_only_uses_runner_marker_line()
    print("check_goal_agent_manager ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
