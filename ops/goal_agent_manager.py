#!/usr/bin/env python3
"""Manage the current gotouhou sustained goal agents.

The current operating model is agent-based, not path-slice-based. Codex `/goal`
mode is responsible for sustained iteration; this manager only prepares persona
documents, starts missing or failed agents, records status, and feeds the
three-hour audit mail. A separate systemd timer should call this manager every
15 minutes so agent supervision is not coupled to the mail cadence.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_REPOS = ("docs", "SpellKard", "Gensoulkyo", "PhK-BattleServer", "PhK-Protocol")
DEFAULT_KEY_FILE = "/root/.codex/keys"
DEFAULT_GODOT_LINUX = "/root/gotouhou/Godot_v4.7-stable_linux.x86_64"
DEFAULT_PROXY = "socks5://10.10.10.108:10808"
GITHUB_ORG = "Phantasm-Klash"
REPORT_INTERVAL_HOURS = 3
PROJECT_COMPLETION_PERCENT = 38
UTC = dt.timezone.utc


AGENTS: dict[str, dict[str, Any]] = {
    "client-agent": {
        "nickname": "Reimu",
        "repo": "SpellKard",
        "key_aliases": ("spellkard", "other"),
        "branch": "agent/client-agent/persistent",
        "summary": "客户端核心弹幕玩法、游戏性功能、Godot UI 和服务端接口对齐。",
        "docs": (
            "docs/dev/progress.md",
            "docs/dev/gotouhou/01_core_stg_client/bullet_pattern_system.md",
            "docs/dev/gotouhou/01_core_stg_client/performance_and_bullet_limits.md",
            "docs/dev/gotouhou/02_networked_match/deterministic_lockstep_review.md",
            "docs/dev/gotouhou/05_content_assets_ui/ui_screens.md",
            "docs/dev/gotouhou/08_game_modes/world_boss_mode.md",
            "docs/dev/gotouhou/08_game_modes/instance_boss_mode.md",
        ),
        "checks": (
            "python3 tools/ci_static_checks.py",
            f"{DEFAULT_GODOT_LINUX} --headless --path godot --script ../tools/client_smoke_test.gd",
            f"{DEFAULT_GODOT_LINUX} --headless --path godot --script ../tools/boss_pattern_catalog_check.gd",
            f"{DEFAULT_GODOT_LINUX} --headless --path godot --script ../tools/client_ui_smoke_test.gd",
        ),
        "mission": (
            "根据 docs 规划生成客户端所需功能、服务端对齐接口和协议内容；在当前客户端基础上继续实现核心弹幕玩法、"
            "Boss/实例/世界 Boss 本地展示、Replay/练习验证、输入与 UI 可用性。线上伤害、奖励和结算必须继续服从服务端权威。"
        ),
    },
    "battle-server-agent": {
        "nickname": "Youmu",
        "repo": "PhK-BattleServer",
        "key_aliases": ("phk", "battle-server", "battle", "other"),
        "branch": "agent/battle-server-agent/persistent",
        "summary": "C++ 战斗服、对战房间、即时创建/清退、Boss 服生成与结算模式。",
        "docs": (
            "docs/dev/progress.md",
            "docs/dev/gotouhou/00_overview/network_security_and_server_split_plan.md",
            "docs/dev/gotouhou/02_networked_match/deterministic_lockstep_review.md",
            "docs/dev/gotouhou/08_game_modes/mode_shared_server_interfaces.md",
            "docs/dev/gotouhou/08_game_modes/world_boss_mode.md",
            "docs/dev/gotouhou/08_game_modes/instance_boss_mode.md",
        ),
        "checks": (
            "python3 tools/check_battle_server.py",
            "docker-compose run --rm test",
            "python3 /root/gotouhou/docs/ops/protocol_audit_check.py",
        ),
        "mission": (
            "根据 docs 与协议规划实现 C++ 战斗服。该服务器负责 60Hz 权威模拟、对战房间生命周期、即时创建/清退、"
            "Boss 服/实例 Boss/世界 Boss 战斗实例生成、输入校验、Replay/hash 和结算签名。不得写库存、钱包、奖励或业务数据库。"
        ),
    },
    "nakama-server-agent": {
        "nickname": "Patchouli",
        "repo": "Gensoulkyo",
        "key_aliases": ("gensoulkyo", "other"),
        "branch": "agent/nakama-server-agent/persistent",
        "summary": "Nakama 业务服、PVP 匹配队列、对战资格验证、大厅和战斗票据。",
        "docs": (
            "docs/dev/progress.md",
            "docs/dev/gotouhou/00_overview/network_security_and_server_split_plan.md",
            "docs/dev/gotouhou/04_server_database_economy/server_stack.md",
            "docs/dev/gotouhou/04_server_database_economy/client_server_connection.md",
            "docs/dev/gotouhou/08_game_modes/mode_shared_server_interfaces.md",
        ),
        "checks": (
            "go test ./runtime/... ./cmd/gensoulkyo_nakama",
            "docker-compose --profile test run --rm test",
            "python3 /root/gotouhou/docs/ops/protocol_audit_check.py",
        ),
        "mission": (
            "根据 docs 与协议规则完善 Nakama 服务端功能，包括 PVP 匹配队列、对战资格验证、battle allocation/ticket、"
            "大厅/房间状态、结算验签、审计持久化和客户端 RPC/WSS 合同。不得把高频 tick 或客户端提交结果做成 Go 生产权威路径。"
        ),
    },
    "audit-agent": {
        "nickname": "Keine",
        "repo": "docs",
        "key_aliases": ("audit", "docs", "ops", "other"),
        "branch": "",
        "summary": "中文审计 git 提交、agent 方向和整体进度，生成三小时汇报内容。",
        "docs": (
            "docs/dev/progress.md",
            "docs/dev/gotouhou",
            "docs/ops",
        ),
        "checks": (
            "python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py",
            "python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou",
        ),
        "mission": (
            "以中文审计各 agent 的 git 提交内容、分支/PR/测试证据是否符合 docs/dev 方向，评估整体开发进度、停滞、"
            "token 消耗风险和是否还有旧 agent 应清退或重新规划。三小时邮件正文优先使用本 agent 的审计报告。"
        ),
    },
    "project-manager-agent": {
        "nickname": "Yukari",
        "repo": "docs",
        "key_aliases": ("manager", "project-manager", "pm", "ops", "docs", "other"),
        "branch": "agent/project-manager-agent/persistent",
        "summary": "项目推进与自动调度，读取 docs/dev、agent 日志、git/PR 状态并调整 agent 方向。",
        "docs": (
            "docs/dev/progress.md",
            "docs/dev/gotouhou",
            "docs/ops/README.md",
            "docs/ops/goal_agent_manager.py",
        ),
        "checks": (
            "python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py",
            "python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start",
            "python3 docs/ops/hourly_progress_mail.py --dry-run --brief",
        ),
        "mission": (
            "作为项目推进和自动调度 agent，持续读取 docs/dev 路线、各 agent 日志、git 状态、PR 状态、回归结果和阻塞项；"
            "把客户端、战斗服、Nakama、审计 agent 的下一步任务收敛成可执行小切片，必要时更新 persona/prompt，"
            "推动阶段性 commit、branch/PR、测试和合并节奏。只按 agent 身份管理，不恢复 scope/路径分片概念。"
        ),
    },
}

MANAGED_AGENT_IDS = tuple(AGENTS.keys())


def utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


def iso(value: dt.datetime) -> str:
    return value.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def run_command(
    command: list[str],
    cwd: Path,
    *,
    timeout: int = 30,
    env: dict[str, str] | None = None,
) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 124, str(exc)
    return completed.returncode, completed.stdout.strip()


def command_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HOME", "/root")
    env.setdefault("XDG_CONFIG_HOME", "/root/.config")
    env.setdefault("GH_CONFIG_DIR", "/root/.config/gh")
    env.setdefault("GOCACHE", "/root/.cache/go-build")
    env.setdefault("GOPATH", "/root/go")
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        # The host shell may still export a stale proxy value that breaks gh.
        env[name] = DEFAULT_PROXY
    if extra:
        env.update(extra)
    return env


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    tmp.replace(path)


def load_keyring(path: Path) -> dict[str, str]:
    aliases: dict[str, str] = {}
    if not path.exists():
        return aliases
    for index, raw_line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" in stripped and not stripped.startswith("sk-"):
            alias, value = stripped.split(":", 1)
        elif "=" in stripped:
            alias, value = stripped.split("=", 1)
        else:
            alias, value = f"key{index}", stripped
        aliases[alias.strip()] = value.strip()
    return aliases


def select_key_alias(agent: dict[str, Any], keyring: dict[str, str]) -> dict[str, Any]:
    preferences = tuple(str(item) for item in agent.get("key_aliases", ()))
    for alias in preferences:
        if alias in keyring:
            return {"alias": alias, "available": True, "preferences": preferences}
    return {"alias": preferences[-1] if preferences else "", "available": False, "preferences": preferences}


def shell_export(name: str, value: str) -> str:
    return f"export {name}={shlex.quote(value)}"


def persona_text(agent_id: str, agent: dict[str, Any], workdir: Path, key_alias: str) -> str:
    docs = "\n".join(f"- `/root/gotouhou/{item}`" for item in agent.get("docs", ()))
    checks = "\n".join(f"- `{item}`" for item in agent.get("checks", ()))
    return f"""# {agent_id} 人格文档

昵称：{agent["nickname"]}
运行模式：Codex `/goal` 持续目标模式
独立工作环境：`{workdir}`
Key alias：`{key_alias or "(missing)"}`

## 使命

{agent["mission"]}

## 工作方式

- 先读 docs/dev，再读当前仓库代码和未完成提交；不要凭旧记忆写代码。
- 每轮必须产生可核验推进：代码提交、测试结果、PR/阻塞说明、或中文审计报告。
- 完成一个小切片后继续选择下一个 docs/dev 优先级切片迭代；不要因为一次提交或一次报告就正常退出。只有遇到硬阻塞、模型/系统容量限制、权限/网络不可恢复失败时才写明原因并退出。
- 发现中断后从本地 worktree、日志、PR 和最新 `origin/main` 恢复；不得回滚他人改动。
- 小而直接、单仓、可本地验证的改动可以阶段性提交；复杂、跨仓、协议/网络/安全、回归修复、多人并行改动走 branch + PR。
- 提交或推送前使用对应 git lock，避免同仓并发。
- 最终状态写到 `/root/gotouhou/.agents/logs/{agent_id}-final.md`。
- 不泄露 `/root/.codex/keys`、SMTP 密码、token、私钥或任何原始凭据。

## 必读文档

{docs}

## 验证优先级

{checks}

## 特别边界

- Godot 服务器无显卡导致的纯 renderer/RenderingDevice 失败可记录为环境 blocked；GDScript parse/compile/type error、脚本加载失败、UI/弹幕合同失败必须修复。
- 服务端使用 `docker-compose` 命令，不使用 `docker compose`。
- 涉及协议、网络、匹配、战斗服、鉴权或安全边界时必须运行 `/root/gotouhou/docs/ops/protocol_audit_check.py`。
"""


def agent_prompt(agent_id: str, agent: dict[str, Any], persona_path: Path, workdir: Path, key_assignment: dict[str, Any]) -> str:
    return f"""你现在是 `{agent_id}`，必须按 Codex `/goal` 持续目标模式工作。

先完整阅读人格文档：`{persona_path}`。

当前独立工作环境：`{workdir}`
工作区总根目录：`/root/gotouhou`
Key alias：`{key_assignment.get("alias") or "(missing)"}`。原始 key 只由 runner 注入环境，禁止打印、写入日志、邮件或 git。

本轮目标：
{agent["mission"]}

强制流程：
1. 读取人格文档列出的 docs/dev 路线和当前仓库代码。
2. 检查 `git status --short --branch`、当前分支、open PR 和已有未提交工作；不要回滚他人改动。
3. 选择一个小而能推进整体项目的功能切片，完成实现或审计。
4. 运行人格文档列出的最小相关检查；服务器端优先 `docker-compose`，协议/网络/安全变更必须跑 protocol audit。
5. 做阶段性 git commit。需要并行评审、跨仓、协议/网络/安全、回归修复或多人协作时推分支并开 PR。
6. 用简短中文写 `/root/gotouhou/.agents/logs/{agent_id}-final.md`，包含完成内容、提交/PR、测试、阻塞风险、下一步。

不要只写计划后退出；完成一个小切片后继续迭代下一个小切片。只有模型容量、网络、权限、branch protection、依赖下载或测试环境硬阻塞时，才写清非敏感原因并退出，等待 manager 检测状态后补救。
"""


def unit_active(unit: str | None) -> bool:
    if not unit:
        return False
    code, output = run_command(["systemctl", "is-active", unit], Path("/"), timeout=10)
    return code == 0 and output.strip() == "active"


def latest_log(root: Path, agent_id: str) -> Path | None:
    logs = sorted((root / ".agents" / "logs").glob(f"{agent_id}-*.log"), key=lambda item: item.stat().st_mtime)
    return logs[-1] if logs else None


def log_info(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"exists": False}
    text = path.read_text(encoding="utf-8", errors="replace")
    exit_status = None
    for match in re.finditer(r"\[goal-manager\] exited status=(\d+)", text):
        exit_status = int(match.group(1))
    token_usage = None
    token_matches = list(re.finditer(r"tokens used\s*\n\s*([0-9,]+)", text, flags=re.IGNORECASE))
    if token_matches:
        token_usage = int(token_matches[-1].group(1).replace(",", ""))
    return {
        "exists": True,
        "path": str(path),
        "updated_at": iso(dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)),
        "bytes": path.stat().st_size,
        "line_count": text.count("\n") + (1 if text else 0),
        "exited": exit_status is not None,
        "exit_status": exit_status,
        "token_usage": token_usage,
        "tail": text[-1200:],
    }


def collect_repo(root: Path, name: str) -> dict[str, Any]:
    repo = root / name
    if not (repo / ".git").exists():
        return {"repo": name, "missing": True, "path": str(repo)}
    branch = run_command(["git", "branch", "--show-current"], repo)[1]
    head = run_command(["git", "rev-parse", "--short", "HEAD"], repo)[1]
    status = run_command(["git", "status", "--short", "--branch"], repo)[1]
    dirty = [line for line in status.splitlines() if line and not line.startswith("## ")]
    recent = run_command(["git", "log", f"--since={REPORT_INTERVAL_HOURS} hours ago", "--oneline", "--max-count=8"], repo)[1]
    return {
        "repo": name,
        "path": str(repo),
        "branch": branch,
        "head": head,
        "status": status,
        "dirty_count": len(dirty),
        "dirty": dirty[:20],
        "commits_last_interval": recent.splitlines() if recent else [],
    }


def collect_pull_requests(root: Path, now: dt.datetime) -> dict[str, Any]:
    prs: dict[str, Any] = {}
    env = command_env()
    for name in DEFAULT_REPOS:
        repo = root / name
        cwd = repo if repo.exists() else root
        code, output = run_command(
            [
                "gh",
                "pr",
                "list",
                "--repo",
                f"{GITHUB_ORG}/{name}",
                "--state",
                "open",
                "--limit",
                "20",
                "--json",
                "number,title,headRefName,baseRefName,mergeStateStatus,isDraft,url,updatedAt,statusCheckRollup",
            ],
            cwd,
            timeout=30,
            env=env,
        )
        try:
            items = json.loads(output) if code == 0 and output else []
        except json.JSONDecodeError:
            items = []
        prs[name] = {
            "repo": name,
            "open_count": len(items) if code == 0 and isinstance(items, list) else None,
            "items": items if code == 0 and isinstance(items, list) else [],
            "status": code,
            "collected_at": iso(now),
            "error": "" if code == 0 else output[-800:],
        }
    return prs


def check_rollup_label(check: dict[str, Any]) -> str:
    for field in ("name", "context", "workflowName", "__typename"):
        value = check.get(field)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unnamed-check"


def check_rollup_counts(item: dict[str, Any]) -> dict[str, Any]:
    counts: dict[str, Any] = {"success": 0, "failed": 0, "pending": 0, "total": 0, "failed_checks": [], "pending_checks": []}
    rollup = item.get("statusCheckRollup")
    if not isinstance(rollup, list):
        return counts
    for raw_check in rollup:
        check = raw_check if isinstance(raw_check, dict) else {}
        counts["total"] += 1
        label = check_rollup_label(check)
        status = str(check.get("status") or "").upper()
        conclusion = str(check.get("conclusion") or "").upper()
        state = str(check.get("state") or "").upper()
        if status and status != "COMPLETED":
            counts["pending"] += 1
            counts["pending_checks"].append(label)
        elif state in {"PENDING", "EXPECTED"}:
            counts["pending"] += 1
            counts["pending_checks"].append(label)
        elif conclusion in {"", "SUCCESS", "SKIPPED", "NEUTRAL"} or state == "SUCCESS":
            counts["success"] += 1
        else:
            counts["failed"] += 1
            counts["failed_checks"].append(label)
    return counts


def check_rollup_detail(checks: dict[str, Any]) -> str:
    parts: list[str] = []
    for key, label in (("failed_checks", "failed"), ("pending_checks", "pending")):
        names = checks.get(key) if isinstance(checks.get(key), list) else []
        if names:
            rendered = ", ".join(str(name) for name in names[:3])
            if len(names) > 3:
                rendered += f", +{len(names) - 3}"
            parts.append(f"{label}=[{rendered}]")
    return " ".join(parts)


def pull_request_owner_agent(repo_name: str, head_ref: object) -> str:
    head = str(head_ref or "")
    if repo_name == "SpellKard":
        return "client-agent"
    if repo_name == "Gensoulkyo":
        return "nakama-server-agent"
    if repo_name == "PhK-BattleServer":
        return "battle-server-agent"
    if repo_name == "PhK-Protocol":
        return "audit-agent"
    if repo_name == "docs":
        if "audit-agent" in head:
            return "audit-agent"
        if "project-manager-agent" in head:
            return "project-manager-agent"
    return "project-manager-agent"


def classify_pull_request_action(item: dict[str, Any], checks: dict[str, int]) -> tuple[int, str, str]:
    if item.get("isDraft"):
        return 70, "draft", "draft: wait until the owning agent marks it ready"
    if checks.get("failed", 0) > 0:
        return 15, "fix_checks", "fix failing checks before merge review"
    merge_state = str(item.get("mergeStateStatus") or "UNKNOWN").upper()
    if merge_state == "DIRTY":
        return 10, "resolve_conflicts", "resolve conflicts or supersede with the current persistent branch"
    if merge_state == "BEHIND":
        return 20, "update_branch", "update branch against main, rerun checks, then review"
    if merge_state in {"BLOCKED", "HAS_HOOKS"}:
        return 30, "blocked_gate", "wait for required review/check gates or branch protection"
    if checks.get("pending", 0) > 0:
        return 40, "wait_checks", "wait for pending checks"
    if merge_state == "CLEAN":
        return 60, "merge_ready", "ready for review/merge"
    return 50, "inspect", f"inspect merge state {merge_state}"


def build_pr_supersede_groups(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in items:
        category = str(item.get("action_category") or "")
        if category not in {"resolve_conflicts", "update_branch"}:
            continue
        key = (str(item.get("repo") or "unknown"), str(item.get("owner_agent") or "unknown"))
        grouped.setdefault(key, []).append(item)

    groups: list[dict[str, Any]] = []
    for (repo, owner_agent), group_items in grouped.items():
        if len(group_items) < 2:
            continue
        states: dict[str, int] = {}
        categories: dict[str, int] = {}
        updated_at_values: list[str] = []
        for item in group_items:
            state = str(item.get("merge_state") or "UNKNOWN")
            category = str(item.get("action_category") or "unknown")
            states[state] = states.get(state, 0) + 1
            categories[category] = categories.get(category, 0) + 1
            updated_at = item.get("updated_at")
            if isinstance(updated_at, str) and updated_at:
                updated_at_values.append(updated_at)
        groups.append(
            {
                "repo": repo,
                "owner_agent": owner_agent,
                "count": len(group_items),
                "numbers": [item.get("number") for item in group_items],
                "merge_states": states,
                "action_categories": categories,
                "oldest_updated_at": min(updated_at_values) if updated_at_values else None,
                "newest_updated_at": max(updated_at_values) if updated_at_values else None,
                "action": "open one fresh current-base PR, or document explicit supersede/close decisions before expanding new work",
            }
        )
    groups.sort(
        key=lambda entry: (
            -int(entry.get("count", 0) or 0),
            str(entry.get("repo", "")),
            str(entry.get("owner_agent", "")),
        )
    )
    return groups


def build_pull_request_queue(pull_requests: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    failed_repos: list[str] = []
    for repo_name, raw_repo in sorted(pull_requests.items()):
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        if not isinstance(repo.get("open_count"), int):
            failed_repos.append(str(repo.get("repo") or repo_name))
            continue
        for raw_item in repo.get("items", []):
            item = raw_item if isinstance(raw_item, dict) else {}
            checks = check_rollup_counts(item)
            priority, action_category, action = classify_pull_request_action(item, checks)
            owner_agent = pull_request_owner_agent(repo_name, item.get("headRefName"))
            items.append(
                {
                    "repo": repo_name,
                    "number": item.get("number"),
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "head": item.get("headRefName"),
                    "base": item.get("baseRefName"),
                    "merge_state": item.get("mergeStateStatus") or "UNKNOWN",
                    "draft": bool(item.get("isDraft")),
                    "updated_at": item.get("updatedAt"),
                    "checks": checks,
                    "priority": priority,
                    "owner_agent": owner_agent,
                    "action_category": action_category,
                    "action": action,
                }
            )
    items.sort(key=lambda entry: (int(entry.get("priority", 99)), str(entry.get("repo", "")), int(entry.get("number") or 0)))
    by_repo: dict[str, int] = {}
    by_state: dict[str, int] = {}
    by_owner: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for item in items:
        repo = str(item.get("repo") or "unknown")
        state = str(item.get("merge_state") or "UNKNOWN")
        owner = str(item.get("owner_agent") or "unknown")
        category = str(item.get("action_category") or "unknown")
        by_repo[repo] = by_repo.get(repo, 0) + 1
        by_state[state] = by_state.get(state, 0) + 1
        by_owner[owner] = by_owner.get(owner, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    supersede_groups = build_pr_supersede_groups(items)
    merge_ready_items = [item for item in items if item.get("action_category") == "merge_ready"]
    return {
        "open_count": len(items),
        "failed_repos": failed_repos,
        "by_repo": by_repo,
        "by_merge_state": by_state,
        "by_owner_agent": by_owner,
        "by_action_category": by_category,
        "supersede_group_count": len(supersede_groups),
        "supersede_groups": supersede_groups,
        "ready_count": len(merge_ready_items),
        "merge_ready_items": merge_ready_items[:8],
        "needs_action_count": sum(1 for item in items if int(item.get("priority", 99)) < 60),
        "items": items,
        "top_items": items[:12],
    }


def prepare_worktree(root: Path, agent_id: str, agent: dict[str, Any], dry_run: bool) -> dict[str, Any]:
    repo_name = str(agent["repo"])
    if repo_name == "docs":
        base_repo = root / "docs"
        branch = str(agent.get("branch") or "")
        if not branch:
            return {"path": str(base_repo), "ready": (base_repo / ".git").exists(), "repo": repo_name, "branch": "main"}
        workdir = root / ".agents" / "worktrees" / agent_id / "docs"
        if (workdir / ".git").exists():
            current_branch = run_command(["git", "branch", "--show-current"], workdir)[1]
            return {"path": str(workdir), "ready": True, "repo": repo_name, "branch": current_branch, "existing": True}
        if dry_run:
            return {"path": str(workdir), "ready": False, "repo": repo_name, "branch": branch, "dry_run": True}
        workdir.parent.mkdir(parents=True, exist_ok=True)
        if workdir.exists() and any(workdir.iterdir()):
            return {"path": str(workdir), "ready": False, "repo": repo_name, "branch": branch, "error": "target exists and is not a git worktree"}
        branch_exists = run_command(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], base_repo)[0] == 0
        command = ["git", "worktree", "add", str(workdir), branch] if branch_exists else ["git", "worktree", "add", "-b", branch, str(workdir), "HEAD"]
        code, output = run_command(command, base_repo, timeout=120)
        return {
            "path": str(workdir),
            "ready": code == 0,
            "repo": repo_name,
            "branch": branch,
            "status": code,
            "output": output[-1000:],
        }
    base_repo = root / repo_name
    workdir = root / ".agents" / "worktrees" / agent_id / repo_name
    branch = str(agent["branch"])
    if (workdir / ".git").exists():
        current_branch = run_command(["git", "branch", "--show-current"], workdir)[1]
        return {"path": str(workdir), "ready": True, "repo": repo_name, "branch": current_branch, "existing": True}
    if dry_run:
        return {"path": str(workdir), "ready": False, "repo": repo_name, "branch": branch, "dry_run": True}
    workdir.parent.mkdir(parents=True, exist_ok=True)
    if workdir.exists() and any(workdir.iterdir()):
        return {"path": str(workdir), "ready": False, "repo": repo_name, "branch": branch, "error": "target exists and is not a git worktree"}
    branch_exists = run_command(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], base_repo)[0] == 0
    command = ["git", "worktree", "add", str(workdir), branch] if branch_exists else ["git", "worktree", "add", "-b", branch, str(workdir), "HEAD"]
    code, output = run_command(command, base_repo, timeout=120)
    return {
        "path": str(workdir),
        "ready": code == 0,
        "repo": repo_name,
        "branch": branch,
        "status": code,
        "output": output[-1000:],
    }


def write_personas(root: Path, agent_id: str, agent: dict[str, Any], workdir: Path, key_assignment: dict[str, Any]) -> dict[str, str]:
    persona_dir = root / ".agents" / "personas"
    prompt_dir = root / ".agents" / "agent-prompts"
    workspace_dir = root / ".agents" / "workspaces" / agent_id
    persona_path = persona_dir / f"{agent_id}.md"
    prompt_path = prompt_dir / f"{agent_id}.md"
    readme_path = workspace_dir / "README.md"
    key_alias = str(key_assignment.get("alias") or "")
    atomic_write_text(persona_path, persona_text(agent_id, agent, workdir, key_alias))
    atomic_write_text(prompt_path, agent_prompt(agent_id, agent, persona_path, workdir, key_assignment))
    atomic_write_text(
        readme_path,
        f"""# {agent_id} 工作环境

- persona: `{persona_path}`
- prompt: `{prompt_path}`
- workdir: `{workdir}`
- repo: `{agent["repo"]}`
- branch: `{agent.get("branch", "")}`
- goal mode: enabled through `codex exec`
""",
    )
    return {"persona": str(persona_path), "prompt": str(prompt_path), "workspace": str(readme_path)}


def should_start_agent(lock: dict[str, Any], log: dict[str, Any], force: bool, now: dt.datetime) -> tuple[bool, str]:
    if force:
        return True, "forced by operator"
    if lock.get("alive"):
        return False, "already running"
    if not log.get("exists"):
        return True, "new agent has no previous run"
    if log.get("exited") and log.get("exit_status") == 0:
        return True, "agent exited cleanly; restart sustained goal agent"
    if log.get("exited") and log.get("exit_status") != 0:
        return True, f"previous run failed with status {log.get('exit_status')}"
    return True, "previous run did not exit cleanly"


def lock_status(root: Path, agent_id: str, now: dt.datetime) -> dict[str, Any]:
    path = root / ".agents" / "locks" / f"{agent_id}.lock.json"
    payload = read_json(path, {}) if path.exists() else {}
    unit = payload.get("unit") if isinstance(payload, dict) else None
    alive = unit_active(unit if isinstance(unit, str) else None)
    age_seconds = None
    started_at = parse_iso(payload.get("started_at") if isinstance(payload, dict) else None)
    if started_at:
        age_seconds = max(0, int((now - started_at).total_seconds()))
    return {
        "path": str(path),
        "exists": path.exists(),
        "unit": unit,
        "alive": alive,
        "age_seconds": age_seconds,
        "started_at": iso(started_at) if started_at else None,
    }


def start_agent(
    root: Path,
    agent_id: str,
    workdir: Path,
    persona_path: Path,
    prompt_path: Path,
    key_assignment: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    key_alias = str(key_assignment.get("alias") or "")
    if not key_assignment.get("available"):
        return {"started": False, "reason": "missing-key-alias", "key_alias": key_alias}
    if dry_run:
        return {"started": False, "reason": "dry-run", "key_alias": key_alias}
    now = utcnow()
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    agents_dir = root / ".agents"
    logs_dir = agents_dir / "logs"
    run_dir = agents_dir / "run"
    locks_dir = agents_dir / "locks"
    logs_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    locks_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / f"{agent_id}-{stamp}.log"
    runner_path = run_dir / f"{agent_id}-{stamp}.sh"
    lock_path = locks_dir / f"{agent_id}.lock.json"
    unit = f"gotouhou-agent-{agent_id}-{stamp}".replace("_", "-")
    script = "\n".join(
        [
            "#!/bin/sh",
            "set -u",
            f"KEY_FILE={shlex.quote(DEFAULT_KEY_FILE)}",
            f"KEY_ALIAS={shlex.quote(key_alias)}",
            shell_export("HOME", "/root"),
            shell_export("XDG_CONFIG_HOME", "/root/.config"),
            shell_export("GH_CONFIG_DIR", "/root/.config/gh"),
            shell_export("GOCACHE", "/root/.cache/go-build"),
            shell_export("GOPATH", "/root/go"),
            shell_export("HTTPS_PROXY", DEFAULT_PROXY),
            shell_export("HTTP_PROXY", DEFAULT_PROXY),
            shell_export("ALL_PROXY", DEFAULT_PROXY),
            shell_export("https_proxy", DEFAULT_PROXY),
            shell_export("http_proxy", DEFAULT_PROXY),
            shell_export("all_proxy", DEFAULT_PROXY),
            "git config --global credential.https://github.com.helper '!/usr/bin/gh auth git-credential' >/dev/null 2>&1 || true",
            "/usr/bin/gh auth setup-git >/dev/null 2>&1 || true",
            "KEY_VALUE=$(/usr/bin/python3 - \"$KEY_FILE\" \"$KEY_ALIAS\" <<'PY'",
            "import sys",
            "path, wanted = sys.argv[1], sys.argv[2]",
            "with open(path, encoding='utf-8', errors='replace') as handle:",
            "    for index, line in enumerate(handle, start=1):",
            "        stripped = line.strip()",
            "        if not stripped or stripped.startswith('#'):",
            "            continue",
            "        if ':' in stripped and not stripped.startswith('sk-'):",
            "            alias, value = stripped.split(':', 1)",
            "        elif '=' in stripped:",
            "            alias, value = stripped.split('=', 1)",
            "        else:",
            "            alias, value = f'key{index}', stripped",
            "        if alias.strip() == wanted:",
            "            print(value.strip())",
            "            raise SystemExit(0)",
            "raise SystemExit(1)",
            "PY",
            ")",
            f"if [ -z \"$KEY_VALUE\" ]; then echo '[goal-manager] missing key alias {key_alias}' >> {shlex.quote(str(log_path))}; exit 2; fi",
            "export OPENAI_API_KEY=\"$KEY_VALUE\" CODEX_API_KEY=\"$KEY_VALUE\"",
            "unset KEY_VALUE",
            f"trap 'rm -f {shlex.quote(str(lock_path))}' EXIT",
            f"echo '[goal-manager] started {agent_id} at {iso(now)}' >> {shlex.quote(str(log_path))}",
            f"echo '[goal-manager] persona {persona_path}' >> {shlex.quote(str(log_path))}",
            f"cd {shlex.quote(str(workdir))}",
            f"/root/.local/bin/codex exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check --add-dir {shlex.quote(str(root))} -C {shlex.quote(str(workdir))} - < {shlex.quote(str(prompt_path))} >> {shlex.quote(str(log_path))} 2>&1",
            "status=$?",
            f"echo '[goal-manager] exited status='$status >> {shlex.quote(str(log_path))}",
            "exit $status",
        ]
    )
    runner_path.write_text(script + "\n", encoding="utf-8", newline="\n")
    runner_path.chmod(0o700)
    write_json(
        lock_path,
        {
            "agent": agent_id,
            "unit": unit,
            "started_at": iso(now),
            "runner_path": str(runner_path),
            "log_path": str(log_path),
            "persona_path": str(persona_path),
            "prompt_path": str(prompt_path),
            "cwd": str(workdir),
            "key_alias": key_alias,
        },
    )
    code, output = run_command(
        [
            "/usr/bin/systemd-run",
            "--unit",
            unit,
            "--collect",
            "--property=WorkingDirectory=" + str(workdir),
            "/bin/sh",
            str(runner_path),
        ],
        workdir,
        timeout=30,
    )
    if code != 0:
        try:
            lock_path.unlink()
        except OSError:
            pass
        return {"started": False, "reason": "systemd-run-failed", "status": code, "output": output[-1000:], "key_alias": key_alias}
    return {
        "started": True,
        "reason": "spawned",
        "unit": unit,
        "log_path": str(log_path),
        "runner_path": str(runner_path),
        "key_alias": key_alias,
        "output": output[-1000:],
    }


def collect_runtime(root: Path) -> dict[str, Any]:
    godot = Path(DEFAULT_GODOT_LINUX)
    godot_code, godot_output = (127, "missing")
    if godot.exists() and os.access(godot, os.X_OK):
        godot_code, godot_output = run_command([str(godot), "--version"], root, timeout=20)
    docker_code, docker_output = run_command(["docker", "--version"], root, timeout=20)
    compose_code, compose_output = run_command(["docker-compose", "--version"], root, timeout=20)
    return {
        "godot_linux": {
            "path": str(godot),
            "exists": godot.exists(),
            "executable": os.access(godot, os.X_OK),
            "version_status": godot_code,
            "version": godot_output.splitlines()[0] if godot_output else "",
        },
        "docker": {
            "available": docker_code == 0,
            "version": docker_output.splitlines()[0] if docker_output else "",
            "docker_compose_available": compose_code == 0,
            "docker_compose_version": compose_output.splitlines()[0] if compose_output else "",
        },
    }


def collect_legacy_agents(root: Path) -> dict[str, Any]:
    code, units = run_command(["systemctl", "list-units", "gotouhou-agent-*", "--all", "--no-pager", "--plain"], root, timeout=20)
    roster = read_json(root / ".agents" / "agent-roster.json", {})
    old_records: list[str] = []
    records = roster.get("scopes") if isinstance(roster, dict) else {}
    if isinstance(records, dict):
        old_records = sorted(str(item) for item in records)
    return {
        "systemd_status": code,
        "systemd_units": units.splitlines()[:80],
        "old_roster_records": old_records,
        "old_roster_record_count": len(old_records),
    }


def build_audit_report(summary: dict[str, Any]) -> str:
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    repos = summary.get("repos") if isinstance(summary.get("repos"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    legacy = summary.get("legacy_agents") if isinstance(summary.get("legacy_agents"), dict) else {}
    regression = summary.get("regression") if isinstance(summary.get("regression"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}
    pull_request_queue = summary.get("pull_request_queue") if isinstance(summary.get("pull_request_queue"), dict) else {}

    active = [agent_id for agent_id, agent in agents.items() if isinstance(agent, dict) and agent.get("status") == "running"]
    failed = [agent_id for agent_id, agent in agents.items() if isinstance(agent, dict) and agent.get("status") == "failed"]
    dirty_repos = [
        f"{name}({repo.get('dirty_count')})"
        for name, repo in repos.items()
        if isinstance(repo, dict) and int(repo.get("dirty_count", 0) or 0) > 0
    ]
    open_pr_count = 0
    pr_failed_repos: list[str] = []
    for repo in pull_requests.values():
        if not isinstance(repo, dict):
            continue
        if isinstance(repo.get("open_count"), int):
            open_pr_count += int(repo["open_count"])
        else:
            pr_failed_repos.append(str(repo.get("repo") or "unknown"))
    if pr_failed_repos:
        pr_line = (
            f"- 当前 open PR 数：未知（{len(pr_failed_repos)} 个仓库采集失败："
            f"{'、'.join(pr_failed_repos[:10])}；已采集可见 open PR 数：{open_pr_count}）。"
        )
    else:
        pr_line = f"- 当前 open PR 数：{open_pr_count}。"

    pr_queue_lines = [
        (
            "- PR 行动队列："
            f"needs_action={pull_request_queue.get('needs_action_count', 'unknown')}；"
            f"ready={pull_request_queue.get('ready_count', 'unknown')}；"
            f"by_repo={pull_request_queue.get('by_repo', {})}；"
            f"by_state={pull_request_queue.get('by_merge_state', {})}；"
            f"by_owner={pull_request_queue.get('by_owner_agent', {})}；"
            f"by_action={pull_request_queue.get('by_action_category', {})}；"
            f"supersede_groups={pull_request_queue.get('supersede_group_count', 0)}。"
        )
    ]
    for group in pull_request_queue.get("supersede_groups", [])[:4]:
        if isinstance(group, dict):
            pr_queue_lines.append(
                "- "
                f"{group.get('owner_agent')} -> {group.get('repo')} stale group "
                f"count={group.get('count')} prs={group.get('numbers')} "
                f"states={group.get('merge_states')} action={group.get('action')}"
            )
    for item in pull_request_queue.get("merge_ready_items", [])[:6]:
        if isinstance(item, dict):
            checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
            check_detail = check_rollup_detail(checks)
            detail_text = f" {check_detail}" if check_detail else ""
            pr_queue_lines.append(
                "- "
                f"merge-ready {item.get('owner_agent')} -> {item.get('repo')} #{item.get('number')} "
                f"checks={checks.get('success', 0)}/{checks.get('failed', 0)}/{checks.get('pending', 0)}"
                f"{detail_text} {item.get('url')}"
            )
    for item in pull_request_queue.get("top_items", [])[:8]:
        if isinstance(item, dict):
            checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
            check_detail = check_rollup_detail(checks)
            detail_text = f" {check_detail}" if check_detail else ""
            pr_queue_lines.append(
                "- "
                f"{item.get('owner_agent')} -> {item.get('repo')} #{item.get('number')} {item.get('merge_state')} "
                f"checks={checks.get('success', 0)}/{checks.get('failed', 0)}/{checks.get('pending', 0)}"
                f"{detail_text} action={item.get('action_category')}:{item.get('action')} {item.get('url')}"
            )

    agent_lines = []
    for agent_id, raw_agent in sorted(agents.items()):
        agent = raw_agent if isinstance(raw_agent, dict) else {}
        agent_lines.append(
            f"- {agent_id}: {agent.get('status')}；repo={agent.get('repo')}；workdir={agent.get('workdir')}；"
            f"key={agent.get('key_alias')}；reason={agent.get('reason')}。"
        )

    action_lines = []
    for action in actions[:12]:
        if isinstance(action, dict):
            result = action.get("result") if isinstance(action.get("result"), dict) else {}
            action_lines.append(
                f"- {action.get('agent', 'manager')}: {action.get('type')}；started={result.get('started', False)}；{action.get('reason', '')}"
            )
    if not action_lines:
        action_lines.append("- 本轮没有新增启动动作。")

    old_records = legacy.get("old_roster_records") if isinstance(legacy.get("old_roster_records"), list) else []
    if old_records:
        cleanup_line = "- 旧 roster 记录已不再作为调度依据：" + "、".join(str(item) for item in old_records[:20]) + "。"
    else:
        cleanup_line = "- 未发现旧 roster 记录。"

    return "\n".join(
        [
            "# gotouhou 审计 agent 三小时汇报",
            "",
            f"审计时间：{summary.get('generated_at', '')}",
            "",
            "## 结论",
            "",
            f"- 已将开发管理模型收敛为 {len(MANAGED_AGENT_IDS)} 个 agent：{', '.join(MANAGED_AGENT_IDS)}。",
            "- 已去除旧分片调度概念；manager 只检测 agent 状态，非运行即补启，运行中不打断；15 分钟 supervisor 独立于三小时邮件。",
            f"- 当前运行中：{', '.join(active) if active else '无'}；失败：{', '.join(failed) if failed else '无'}。",
            f"- 整体完成度仍按约 {PROJECT_COMPLETION_PERCENT}% 估算；主线仍是 Phase 3 服务器权威在线 MVP，同时补 Phase 2/6/8 客户端弹幕与 UI。",
            cleanup_line,
            "",
            "## 新 agent 状态",
            "",
            *agent_lines,
            "",
            "## 本轮动作",
            "",
            *action_lines,
            "",
            "## Git 与版本风险",
            "",
            f"- 当前 dirty 仓库：{', '.join(dirty_repos) if dirty_repos else '无'}。",
            pr_line,
            *pr_queue_lines,
            "- 新 agent 使用独立 worktree/工作目录，避免直接覆盖旧 agent 未提交内容；审计 agent 继续判断旧 dirty work 是否应整理成 PR 或废弃。",
            "- 简单线性改动可阶段性提交；跨仓、协议/网络/安全、回归修复和并行开发必须 branch + PR。",
            "",
            "## 回归与环境",
            "",
            f"- 最新 regression：ok={regression.get('ok', 'unknown')}，failed={regression.get('failed_count', 'unknown')}。",
            "- 服务端回归使用 `docker-compose`；Godot 纯渲染器/RenderingDevice 缺 GPU 失败可忽略，脚本/合同失败不能忽略。",
            "",
            "## 下个三小时方向",
            "",
            "- client-agent：优先把弹幕玩法、Boss/实例/世界 Boss 本地合同、Replay/练习和服务端协议字段对齐到可 headless 验证状态。",
            "- battle-server-agent：优先推进房间生命周期、Boss 战斗实例、输入窗口、Replay/hash、结算签名和 protocol audit。",
            "- nakama-server-agent：优先推进 PVP 匹配队列、资格验证、battle ticket/allocation、Nakama RPC/WSS 合同和 PostgreSQL audit。",
            "- audit-agent：继续用中文审计提交和方向，三小时邮件只保留结论、阻塞和下一步，不再粘贴长日志。",
            "- project-manager-agent：每轮读取 docs/dev、日志、PR、回归和 git 状态，主动给各 agent 收敛下一步任务、提示词和版本流程。",
        ]
    ) + "\n"


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    now = utcnow()
    agents_dir = root / ".agents"
    keyring = load_keyring(Path(args.key_file).resolve())
    previous = read_json(agents_dir / "goal-agent-summary.json", {})

    repos = {name: collect_repo(root, name) for name in DEFAULT_REPOS}
    pull_requests = collect_pull_requests(root, now)
    pull_request_queue = build_pull_request_queue(pull_requests)
    runtime = collect_runtime(root)
    regression = read_json(root / ".agents" / "checks" / "latest-regression.json", {"missing": True})
    legacy_agents = collect_legacy_agents(root)
    agents: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []

    for agent_id, agent in AGENTS.items():
        key_assignment = select_key_alias(agent, keyring)
        worktree = prepare_worktree(root, agent_id, agent, args.dry_run)
        workdir = Path(str(worktree["path"]))
        paths = write_personas(root, agent_id, agent, workdir, key_assignment) if not args.dry_run else {
            "persona": str(root / ".agents" / "personas" / f"{agent_id}.md"),
            "prompt": str(root / ".agents" / "agent-prompts" / f"{agent_id}.md"),
            "workspace": str(root / ".agents" / "workspaces" / agent_id / "README.md"),
        }
        lock = lock_status(root, agent_id, now)
        log = log_info(latest_log(root, agent_id))
        start, reason = should_start_agent(lock, log, args.force_start, now)
        result: dict[str, Any] | None = None
        if start and not lock.get("alive") and worktree.get("ready", False):
            result = start_agent(
                root,
                agent_id,
                workdir,
                Path(paths["persona"]),
                Path(paths["prompt"]),
                key_assignment,
                args.dry_run or args.no_start,
            )
            actions.append({"type": "start-goal-agent", "agent": agent_id, "reason": reason, "result": result})
            lock = lock_status(root, agent_id, utcnow())
            log = log_info(latest_log(root, agent_id))
        elif start and not worktree.get("ready", False):
            actions.append({"type": "worktree-blocked", "agent": agent_id, "reason": str(worktree.get("error") or worktree.get("output") or "worktree not ready")})

        status = "running" if lock.get("alive") else "missing"
        if not lock.get("alive") and log.get("exited"):
            status = "completed" if log.get("exit_status") == 0 else "failed"
        elif not lock.get("alive") and log.get("exists"):
            status = "stopped"
        agents[agent_id] = {
            "agent": agent_id,
            "nickname": agent["nickname"],
            "repo": agent["repo"],
            "summary": agent["summary"],
            "workdir": str(workdir),
            "worktree": worktree,
            "persona_path": paths["persona"],
            "prompt_path": paths["prompt"],
            "workspace_path": paths["workspace"],
            "key_alias": key_assignment.get("alias"),
            "key_available": key_assignment.get("available"),
            "lock": lock,
            "runtime_log": log,
            "status": status,
            "progress": bool(lock.get("alive") or log.get("bytes", 0) or (result or {}).get("started")),
            "reason": reason,
        }

    summary = {
        "version": 2,
        "manager": "goal_agent_manager",
        "generated_at": iso(utcnow()),
        "report_interval_hours": REPORT_INTERVAL_HOURS,
        "project_completion_percent": PROJECT_COMPLETION_PERCENT,
        "root": str(root),
        "dry_run": bool(args.dry_run),
        "resampled_after_actions": True,
        "repos": repos,
        "pull_requests": pull_requests,
        "pull_request_queue": pull_request_queue,
        "runtime": runtime,
        "regression": regression,
        "legacy_agents": legacy_agents,
        "agents": agents,
        "actions": actions,
        "action_count": len(actions),
        "started_count": sum(1 for item in actions if (item.get("result") or {}).get("started")),
        "failures": [item for item in actions if item.get("result") and not item["result"].get("started") and item["result"].get("reason") != "dry-run"],
        "previous_generated_at": previous.get("generated_at") if isinstance(previous, dict) else None,
    }
    audit_text = build_audit_report(summary)
    reports_dir = root / ".agents" / "reports"
    audit_path = reports_dir / "audit-agent-latest.md"
    plan_path = reports_dir / "plan-audit-latest.md"
    if not args.dry_run:
        atomic_write_text(audit_path, audit_text)
        atomic_write_text(plan_path, audit_text)
    summary["reports"] = {
        "plan_audit": {
            "path": str(plan_path),
            "updated_at": iso(utcnow()),
            "text": audit_text[:3000],
        },
        "audit_report": {
            "path": str(audit_path),
            "updated_at": iso(utcnow()),
            "text": audit_text[:3000],
        },
    }
    if not args.dry_run:
        write_json(agents_dir / "goal-agent-summary.json", summary)
        write_json(agents_dir / "last-watchdog-summary.json", summary)
        snapshot_dir = agents_dir / "hourly-snapshots"
        write_json(snapshot_dir / f"{now.strftime('%Y%m%dT%H%M%SZ')}-goal-agents.json", summary)
        write_manager_status(root, summary)
    return summary


def write_manager_status(root: Path, summary: dict[str, Any]) -> None:
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    lines = [
        "# gotouhou goal agent manager status",
        "",
        f"Updated: {summary.get('generated_at')}",
        "Mode: codex-/goal-active",
        f"Managed agents: {', '.join(MANAGED_AGENT_IDS)}",
        "Model: agent status detection only; non-running agents are restarted; no path-slice scheduling or progress heuristics.",
        "Supervisor cadence: 15 minutes; mail cadence: 3 hours.",
        "",
        "| Agent | Repo | Status | Key alias | Workdir | Persona |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for agent_id, raw_agent in sorted(agents.items()):
        agent = raw_agent if isinstance(raw_agent, dict) else {}
        lines.append(
            f"| {agent_id} | {agent.get('repo')} | {agent.get('status')} | {agent.get('key_alias')} | "
            f"{agent.get('workdir')} | {agent.get('persona_path')} |"
        )
    atomic_write_text(root / ".agents" / "manager-status.md", "\n".join(lines) + "\n")
    write_json(
        root / ".agents" / "manager-heartbeat.json",
        {
            "source": "goal_agent_manager",
            "updated_at": summary.get("generated_at"),
            "mode": "codex-/goal-active",
            "agent_count": len(agents),
            "started_count": summary.get("started_count", 0),
            "summary_path": str(root / ".agents" / "goal-agent-summary.json"),
        },
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/root/gotouhou")
    parser.add_argument("--key-file", default=DEFAULT_KEY_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-start", action="store_true", help="write state/personas without launching codex workers")
    parser.add_argument("--force-start", action="store_true", help="start agents even if they completed recently")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    summary = build_summary(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
