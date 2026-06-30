#!/usr/bin/env python3
"""Lightweight invariants for goal agent manager summary shaping."""

from __future__ import annotations

import sys
import tempfile
import os
import datetime as dt
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


def check_running_log_staleness_becomes_resource_risk() -> None:
    now = dt.datetime(2026, 6, 30, 16, 0, tzinfo=goal_agent_manager.UTC)
    stale_at = now - dt.timedelta(seconds=goal_agent_manager.RUNNING_LOG_STALE_HIGH_SECONDS + 60)
    summary = goal_agent_manager.build_agent_resource_risk(
        {
            "project-manager-agent": {
                "repo": "docs",
                "status": "running",
                "runtime_log": {
                    "token_usage": None,
                    "bytes": 1200,
                    "updated_at": goal_agent_manager.iso(stale_at),
                },
            }
        },
        {"old_roster_records": [], "legacy_log_prefixes": []},
        now,
    )

    item = summary["items"][0]
    assert item["agent"] == "project-manager-agent"
    assert item["severity"] == "high"
    assert item["log_age_seconds"] >= goal_agent_manager.RUNNING_LOG_STALE_HIGH_SECONDS
    assert any("running_log_stale_seconds" in reason for reason in item["reasons"])
    assert "关键错误" in item["action"]
    assert "阻塞" in item["action"]


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


def check_managed_worktree_state_becomes_agent_actions() -> None:
    agents = {
        "client-agent": {
            "repo": "SpellKard",
            "worktree_state": {
                "missing": False,
                "path": "/tmp/SpellKard",
                "branch": "agent/client-agent/persistent",
                "head": "abc1234",
                "dirty_count": 2,
                "dirty": [" M godot/project.godot", "?? godot/tests/new_test.gd"],
                "ahead": 3,
                "behind": 0,
                "upstream_gone": False,
            },
        },
        "battle-server-agent": {
            "repo": "PhK-BattleServer",
            "worktree_state": {
                "missing": False,
                "path": "/tmp/PhK-BattleServer",
                "branch": "agent/battle-server-agent/persistent",
                "head": "def5678",
                "dirty_count": 0,
                "dirty": [],
                "ahead": 0,
                "behind": 1,
                "upstream_gone": True,
                "tracking": "origin/agent/battle-server-agent/current-20260630-1824",
            },
        },
    }

    actions = goal_agent_manager.build_next_agent_actions(
        {"items": [], "top_items": [], "merge_ready_items": [], "supersede_groups": []},
        {"top_items": []},
        {"top_items": []},
        agents,
    )

    categories = {(item["agent"], item["category"]) for item in actions["items"]}
    assert ("client-agent", "managed_worktree_dirty") in categories
    assert ("client-agent", "managed_worktree_ahead") in categories
    assert ("battle-server-agent", "managed_worktree_behind") in categories
    assert ("battle-server-agent", "managed_worktree_upstream_gone") in categories
    assert actions["by_agent"]["client-agent"] == 2
    assert actions["by_agent"]["battle-server-agent"] == 2
    assert any("先收敛当前代码切片" in item["action"] for item in actions["items"])
    assert any("不要继续堆 only-local 提交" in item["action"] for item in actions["items"])
    assert any("已删除" in item["action"] for item in actions["items"])


def check_upstream_gone_status_becomes_repo_and_health_risk() -> None:
    status = "## agent/battle-server-agent/current-20260630-1824...origin/agent/battle-server-agent/current-20260630-1824 [gone]"
    branch_info = goal_agent_manager.repo_status_branch_info(status)
    assert branch_info["upstream_gone"] is True
    assert branch_info["tracking"] == "origin/agent/battle-server-agent/current-20260630-1824"

    repo_state = goal_agent_manager.build_repo_state_risk(
        {
            "PhK-BattleServer": {
                "repo": "PhK-BattleServer",
                "branch": "agent/battle-server-agent/current-20260630-1824",
                "head": "e1549aa",
                "status": status,
                "dirty_count": 0,
                "dirty": [],
            }
        }
    )
    upstream_items = [item for item in repo_state["items"] if item["category"] == "upstream_gone"]
    assert upstream_items
    assert upstream_items[0]["evidence"]["tracking"] == "origin/agent/battle-server-agent/current-20260630-1824"

    agents = {
        agent_id: {
            "repo": goal_agent_manager.AGENTS[agent_id]["repo"],
            "status": "running",
            "progress": True,
            "key_available": True,
            "worktree_state": {
                "missing": False,
                "dirty_count": 0,
                "ahead": 0,
                "behind": 0,
                "upstream_gone": agent_id == "battle-server-agent",
            },
        }
        for agent_id in goal_agent_manager.MANAGED_AGENT_IDS
    }
    health = goal_agent_manager.build_agent_health(agents, repo_state, {"items": []}, {"items": []}, {"items": []})
    battle = health["agents"]["battle-server-agent"]
    assert any("upstream gone" in reason for reason in battle["reasons"])
    assert any("切回最新 origin/main" in action for action in battle["actions"])


def check_repo_state_health_actions_are_actionable_chinese() -> None:
    agents = {
        agent_id: {
            "repo": goal_agent_manager.AGENTS[agent_id]["repo"],
            "status": "running",
            "progress": True,
            "key_available": True,
            "worktree_state": {"missing": False, "dirty_count": 0, "ahead": 0, "behind": 0},
        }
        for agent_id in goal_agent_manager.MANAGED_AGENT_IDS
    }
    repo_state_risk = {
        "items": [
            {
                "owner_agent": "nakama-server-agent",
                "repo": "Gensoulkyo",
                "priority": 8,
                "category": "dirty_worktree",
                "summary": "Gensoulkyo has 4 uncommitted item(s)",
                "action": "old generic action",
                "evidence": {
                    "branch": "agent/gensoulkyo-lobby/20260629-0900",
                    "dirty_count": 4,
                },
            },
            {
                "owner_agent": "battle-server-agent",
                "repo": "PhK-BattleServer",
                "priority": 65,
                "category": "legacy_branch_checkout",
                "summary": "legacy branch",
                "action": "old generic action",
                "evidence": {"branch": "agent/phk-battle-server/20260629-0030"},
            },
        ],
        "top_items": [],
    }

    health = goal_agent_manager.build_agent_health(
        agents,
        repo_state_risk,
        {"items": []},
        {"items": []},
        {"items": []},
    )

    nakama_actions = health["agents"]["nakama-server-agent"]["actions"]
    battle_actions = health["agents"]["battle-server-agent"]["actions"]
    assert any("先止血版本状态" in action and "dirty=4" in action for action in nakama_actions)
    assert any("不要把 PhK-BattleServer root checkout" in action for action in battle_actions)


def check_project_manager_prompt_sees_global_action_queue() -> None:
    previous = {
        "next_agent_actions": {
            "items": [
                {
                    "agent": "nakama-server-agent",
                    "repo": "Gensoulkyo",
                    "priority": 7,
                    "category": "managed_worktree_ahead",
                    "action": "先推送 ahead 提交并开/更新 PR",
                    "summary": "nakama-server-agent managed worktree is ahead=2",
                },
                {
                    "agent": "battle-server-agent",
                    "repo": "PhK-BattleServer",
                    "priority": 65,
                    "category": "legacy_branch_checkout",
                    "action": "不要把 legacy 分支当基线",
                    "summary": "battle server legacy checkout",
                },
            ]
        }
    }

    manager_prompt = goal_agent_manager.previous_next_action_prompt("project-manager-agent", previous)
    client_prompt = goal_agent_manager.previous_next_action_prompt("client-agent", previous)

    assert "nakama-server-agent managed worktree is ahead=2" in manager_prompt
    assert "battle server legacy checkout" in manager_prompt
    assert "当前没有 manager 写入的结构化下一步行动项" in client_prompt


def check_read_only_samples_do_not_persist_authoritative_state() -> None:
    with tempfile.TemporaryDirectory(prefix="goal-agent-manager-check-") as tmp:
        root = Path(tmp)
        key_file = root / "keys"
        key_file.write_text("other: dummy-local-test-key\n", encoding="utf-8")
        reports_dir = root / ".agents" / "reports"
        reports_dir.mkdir(parents=True)
        old_report_time = dt.datetime(2026, 6, 30, 12, 0, tzinfo=goal_agent_manager.UTC)
        old_report_epoch = old_report_time.timestamp()
        for name in ("audit-agent-latest.md", "plan-audit-latest.md"):
            report = reports_dir / name
            report.write_text("old report\n", encoding="utf-8")
            os.utime(report, (old_report_epoch, old_report_epoch))

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
                assert (root / ".agents" / "reports" / "audit-agent-latest.md").read_text(encoding="utf-8") == "old report\n"
                assert (root / ".agents" / "reports" / "plan-audit-latest.md").read_text(encoding="utf-8") == "old report\n"
                assert summary["reports"]["audit_report"]["updated_at"] == goal_agent_manager.iso(old_report_time)
                assert summary["reports"]["plan_audit"]["updated_at"] == goal_agent_manager.iso(old_report_time)
                assert "text" not in summary["reports"]["audit_report"]
                assert "text" not in summary["reports"]["plan_audit"]
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


def main() -> int:
    check_legacy_resource_risk_is_structured_not_managed()
    check_running_log_staleness_becomes_resource_risk()
    check_recent_large_managed_log_keeps_resource_risk()
    check_agent_health_promotes_version_and_resource_risk()
    check_managed_worktree_state_becomes_agent_actions()
    check_upstream_gone_status_becomes_repo_and_health_risk()
    check_repo_state_health_actions_are_actionable_chinese()
    check_project_manager_prompt_sees_global_action_queue()
    check_read_only_samples_do_not_persist_authoritative_state()
    check_live_lock_log_is_preferred_over_latest_old_log()
    check_exit_status_only_uses_runner_marker_line()
    check_compact_summary_keeps_log_update_time()
    print("check_goal_agent_manager ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
