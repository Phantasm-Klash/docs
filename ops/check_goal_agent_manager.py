#!/usr/bin/env python3
"""Lightweight invariants for goal agent manager summary shaping."""

from __future__ import annotations

import sys
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

    assert health["agents"]["client-agent"]["score"] < health["agents"]["battle-server-agent"]["score"]
    assert "client-agent" not in health["low_score_agents"]
    assert any("资源风险 high" in reason for reason in health["agents"]["client-agent"]["reasons"])
    mail_lines = hourly_progress_mail.agent_health_lines({"agent_health": health})
    assert any("client-agent" in line and "score=" in line for line in mail_lines)


def main() -> int:
    check_legacy_resource_risk_is_structured_not_managed()
    check_agent_health_promotes_version_and_resource_risk()
    print("check_goal_agent_manager ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
