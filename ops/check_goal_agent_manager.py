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


def check_agent_health_promotes_version_and_resource_risk() -> None:
    agents = {
        "client-agent": {
            "repo": "SpellKard",
            "status": "running",
            "progress": True,
            "key_available": True,
        },
        "battle-server-agent": {
            "repo": "PhK-BattleServer",
            "status": "running",
            "progress": True,
            "key_available": True,
        },
        "nakama-server-agent": {
            "repo": "Gensoulkyo",
            "status": "running",
            "progress": True,
            "key_available": True,
        },
        "audit-agent": {
            "repo": "docs",
            "status": "running",
            "progress": True,
            "key_available": True,
        },
        "project-manager-agent": {
            "repo": "docs",
            "status": "running",
            "progress": True,
            "key_available": True,
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
        {"items": []},
        resource_risk,
        next_actions,
    )

    assert health["agents"]["client-agent"]["score"] < health["agents"]["battle-server-agent"]["score"]
    assert "client-agent" not in health["low_score_agents"]
    assert any("资源风险 high" in reason for reason in health["agents"]["client-agent"]["reasons"])
    mail_lines = hourly_progress_mail.agent_health_lines({"agent_health": health})
    assert any("client-agent" in line and "score=" in line for line in mail_lines)


def check_recent_large_managed_log_keeps_resource_risk() -> None:
    summary = goal_agent_manager.build_agent_resource_risk(
        {
            "client-agent": {
                "repo": "SpellKard",
                "status": "running",
                "runtime_log": {"token_usage": None, "bytes": 8_000},
                "recent_log_pressure": {
                    "window_hours": goal_agent_manager.RECENT_LOG_PRESSURE_HOURS,
                    "sample_count": 4,
                    "max_bytes": goal_agent_manager.LOG_BYTES_HIGH_RISK + 10,
                    "medium_count": 2,
                    "high_count": 1,
                },
            }
        },
        {"old_roster_records": [], "legacy_log_prefixes": []},
    )

    item = summary["items"][0]
    assert item["agent"] == "client-agent"
    assert item["severity"] == "high"
    assert item["recent_log_max_bytes"] > goal_agent_manager.LOG_BYTES_HIGH_RISK
    assert item["recent_log_high_count"] == 1
    assert any("recent_log_bytes" in reason for reason in item["reasons"])
    assert "停止复制长日志" in item["action"]


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
    assert "先止血版本状态" in summary["items"][0]["action"]
    assert summary["by_owner_agent"] == {"audit-agent": 1}


def check_repo_state_actions_stop_legacy_dirty_expansion() -> None:
    repo_state_risk = {
        "top_items": [
            {
                "owner_agent": "nakama-server-agent",
                "repo": "Gensoulkyo",
                "priority": 8,
                "category": "dirty_worktree",
                "summary": "Gensoulkyo has 4 uncommitted item(s) on agent/gensoulkyo-lobby/20260629-0900",
                "action": "inspect the dirty work",
                "evidence": {
                    "branch": "agent/gensoulkyo-lobby/20260629-0900",
                    "dirty_count": 4,
                },
            },
            {
                "owner_agent": "nakama-server-agent",
                "repo": "Gensoulkyo",
                "priority": 65,
                "category": "legacy_branch_checkout",
                "summary": "Gensoulkyo root checkout is on legacy/non-managed branch agent/gensoulkyo-lobby/20260629-0900",
                "action": "avoid using this root checkout as the canonical baseline",
                "evidence": {"branch": "agent/gensoulkyo-lobby/20260629-0900"},
            },
        ]
    }

    actions = goal_agent_manager.build_next_agent_actions({"top_items": [], "merge_ready_items": []}, {"top_items": []}, repo_state_risk)
    prompt = goal_agent_manager.previous_next_action_prompt("nakama-server-agent", {"next_agent_actions": actions})

    assert "先止血版本状态" in prompt
    assert "完成前不要扩展新业务切片" in prompt
    assert "不要把 Gensoulkyo root checkout 的 legacy 分支" in prompt
    assert "owning managed agent branch" in prompt

    agents = {
        "client-agent": {"repo": "SpellKard", "status": "running", "progress": True, "key_available": True},
        "battle-server-agent": {"repo": "PhK-BattleServer", "status": "running", "progress": True, "key_available": True},
        "nakama-server-agent": {"repo": "Gensoulkyo", "status": "running", "progress": True, "key_available": True},
        "audit-agent": {"repo": "docs", "status": "running", "progress": True, "key_available": True},
        "project-manager-agent": {"repo": "docs", "status": "running", "progress": True, "key_available": True},
    }
    health = goal_agent_manager.build_agent_health(agents, {"items": repo_state_risk["top_items"]}, {"items": []}, {"items": []}, actions)
    health_actions = "\n".join(health["agents"]["nakama-server-agent"]["actions"])
    assert "先止血版本状态" in health_actions
    assert "不要把 Gensoulkyo root checkout" in health_actions


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


def check_running_agent_prefers_lock_log_path() -> None:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        logs_dir = tmp / ".agents" / "logs"
        logs_dir.mkdir(parents=True)
        old_log = logs_dir / "nakama-server-agent-20260630T150029Z.log"
        new_log = logs_dir / "nakama-server-agent-20260630T152603Z.log"
        old_log.write_text("[goal-manager] exited status=0\ntokens used\n921,256\n", encoding="utf-8")
        new_log.write_text("[goal-manager] started nakama-server-agent\n", encoding="utf-8")

        selected = goal_agent_manager.agent_runtime_log_path(
            tmp,
            "nakama-server-agent",
            {"alive": True, "log_path": str(new_log)},
        )
        running_log = goal_agent_manager.log_info(selected)

    assert selected == new_log
    assert running_log["exited"] is False
    assert running_log["token_usage"] is None


def check_runtime_log_keeps_tail_only_for_failures() -> None:
    with tempfile.TemporaryDirectory() as raw_tmp:
        tmp = Path(raw_tmp)
        running_log = tmp / "client-agent-20260630T153135Z.log"
        failed_log = tmp / "client-agent-20260630T153600Z.log"
        running_log.write_text("normal progress line\n" * 200, encoding="utf-8")
        failed_log.write_text(("failure context line\n" * 200) + "[goal-manager] exited status=1\n", encoding="utf-8")

        running_info = goal_agent_manager.log_info(running_log)
        failed_info = goal_agent_manager.log_info(failed_log)

    assert running_info["sampled_bytes"] <= goal_agent_manager.LOG_SAMPLE_BYTES
    assert "tail" not in running_info
    assert "diagnostic_tail" not in running_info
    assert "tail" not in failed_info
    assert 0 < len(failed_info["diagnostic_tail"]) <= goal_agent_manager.LOG_DIAGNOSTIC_TAIL_CHARS


def check_compact_summary_keeps_log_update_time() -> None:
    compact = goal_agent_manager.compact_summary(
        {
            "agents": {
                "client-agent": {
                    "repo": "SpellKard",
                    "status": "running",
                    "key_alias": "spellkard",
                    "workdir": "/tmp/SpellKard",
                    "runtime_log": {
                        "path": "/tmp/client.log",
                        "updated_at": "2026-06-30T17:08:00Z",
                        "bytes": 1200,
                        "sampled_bytes": 1200,
                        "tail_truncated": False,
                        "token_usage": None,
                        "exit_status": None,
                    },
                }
            }
        }
    )

    log = compact["agents"]["client-agent"]["log"]
    assert log["updated_at"] == "2026-06-30T17:08:00Z"
    assert "diagnostic_tail" not in log


def check_no_start_is_non_authoritative() -> None:
    with tempfile.TemporaryDirectory() as raw_tmp:
        root = Path(raw_tmp)
        (root / ".agents").mkdir()
        for repo_name in goal_agent_manager.DEFAULT_REPOS:
            repo = root / repo_name
            repo.mkdir()
            (repo / ".git").mkdir()

        args = goal_agent_manager.parse_args(["--root", str(root), "--no-start", "--key-file", str(root / "missing-keys")])
        summary = goal_agent_manager.build_summary(args)

        assert summary["read_only_sample"] is True
        assert "non_authoritative_reason" in summary
        assert not (root / ".agents" / "goal-agent-summary.json").exists()
        assert not (root / ".agents" / "last-watchdog-summary.json").exists()
        assert not (root / ".agents" / "manager-heartbeat.json").exists()
        assert not (root / ".agents" / "personas").exists()


def main() -> int:
    check_legacy_resource_risk_is_structured_not_managed()
    check_agent_health_promotes_version_and_resource_risk()
    check_recent_large_managed_log_keeps_resource_risk()
    check_pending_pr_checks_are_not_reported_as_branch_gate()
    check_dirty_repo_owner_prefers_active_workdir_agent()
    check_repo_state_actions_stop_legacy_dirty_expansion()
    check_mail_summary_falls_back_when_primary_is_invalid()
    check_running_agent_prefers_lock_log_path()
    check_runtime_log_keeps_tail_only_for_failures()
    check_compact_summary_keeps_log_update_time()
    check_no_start_is_non_authoritative()
    print("check_goal_agent_manager ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
