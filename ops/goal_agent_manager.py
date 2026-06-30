#!/usr/bin/env python3
"""Manage the current gotouhou sustained goal agents.

The current operating model is agent-based, not path-slice-based. Codex `/goal`
mode is responsible for sustained iteration; this manager prepares persona
documents, starts missing or failed agents, samples live worktree/PR/runtime
state, and feeds identity-based next actions back into the five managed agents.
A separate systemd timer calls this manager every 15 minutes so supervision and
project-manager steering are not coupled to the three-hour mail cadence.
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
TOKEN_MEDIUM_RISK = 200_000
TOKEN_HIGH_RISK = 500_000
LOG_BYTES_MEDIUM_RISK = 1_000_000
LOG_BYTES_HIGH_RISK = 3_000_000
RUNNING_LOG_STALE_MEDIUM_SECONDS = 30 * 60
RUNNING_LOG_STALE_HIGH_SECONDS = 90 * 60
LOG_SAMPLE_BYTES = 64_000
LOG_TAIL_CHARS = 800
PROMPT_MAX_NEXT_ACTION_LINES = 6
PROMPT_MAX_RESOURCE_ACTION_LINES = 2
PROMPT_MAX_TEXT_CHARS = 180


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
            "python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py docs/ops/check_goal_agent_manager.py",
            "python3 docs/ops/check_goal_agent_manager.py",
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
        "summary": "项目推进与自动调度，读取 docs/dev、agent 日志、git/PR 状态并主动推动交付闭环。",
        "docs": (
            "docs/dev/progress.md",
            "docs/dev/gotouhou",
            "docs/ops/README.md",
            "docs/ops/goal_agent_manager.py",
        ),
        "checks": (
            "python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py docs/ops/check_goal_agent_manager.py",
            "python3 docs/ops/check_goal_agent_manager.py",
            "python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start",
            "python3 docs/ops/hourly_progress_mail.py --dry-run --brief",
        ),
        "mission": (
            "作为项目推进和自动调度 agent，持续读取 docs/dev 路线、各 agent 日志、git 状态、PR 状态、回归结果和阻塞项；"
            "把客户端、战斗服、Nakama、审计 agent 的下一步任务收敛成可执行小切片，必要时更新 persona/prompt，"
            "推动阶段性 commit、branch/PR、测试、复采样和合并节奏；对低分、dirty、ahead、PR 堆积或长日志 agent 优先止血。"
            "只管理调度、评分、提示词、审计和版本流程，"
            "不得直接实现客户端/战斗服/Nakama 业务代码。只按 agent 身份管理，不恢复 scope/路径分片概念。"
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


def agent_operating_limits(agent_id: str) -> str:
    common = [
        "- 每轮只推进一个可验证小切片；完成后先 commit/PR/记录测试，再继续下一个切片。",
        "- 最终中文汇报控制在 40 行以内，只写完成内容、提交/PR、测试、阻塞和下一步，不粘贴长日志或大段 diff。",
        "- 单次运行日志或 token 风险升高时立即收敛范围，优先提交已验证工作，不继续扩大任务。",
        "- 发现本地 ahead、dirty、PR 冲突或检查失败时，优先整理版本流程，而不是继续堆新功能。",
    ]
    specific: dict[str, list[str]] = {
        "client-agent": [
            "- 不允许长期停留在 only-local ahead 状态；必须 push/开 PR，或在 final 中写明无法开 PR 的具体原因。",
            "- 若 managed worktree ahead 超过 2 个提交，下一轮首要任务是 push/开 PR/拆小 PR，不能继续堆新功能。",
            "- 优先交付 headless 可验证的弹幕/玩法/协议合同，不把纯渲染失败误判为功能失败。",
        ],
        "battle-server-agent": [
            "- C++ 战斗服只做短切片：房间生命周期、Boss 实例、输入窗口、Replay/hash、结算签名逐项收敛。",
            "- 不复制长编译日志；`docker-compose` 和 protocol audit 只报告通过/失败摘要与关键错误。",
        ],
        "nakama-server-agent": [
            "- 新增 Nakama 功能前先处理 Gensoulkyo 根 checkout 的 dirty/ahead/PR 风险，或明确迁移/废弃理由。",
            "- 如果 Gensoulkyo 根 checkout 仍有 dirty 项，本轮第一步必须给出 disposition：吸收到 managed branch、提交/PR、或写明 supersede/废弃依据；未处理前不要开新功能切片。",
            "- 业务服只负责资格、队列、ticket、回调和审计；不得把高频战斗 tick 做成 Go 权威路径。",
        ],
        "audit-agent": [
            "- 审计默认只读；如需修改 ops/report，使用 docs 独立分支或 worktree，避免覆盖开发 agent 的业务改动。",
            "- 使命是中文方向审计、PR/状态审计、短报告和风险识别；默认不实现业务代码，不复制长日志。",
            "- `--no-start` 只能用于本地只读采样，不能把结果当成权威 watchdog 状态，不能写入 summary。",
        ],
        "project-manager-agent": [
            "- 只做项目推进、调度、评分、提示词和版本流程管理；不得直接实现 client/battle/nakama 业务代码。",
            "- 每轮读取 docs/dev、agent 日志、PR、回归和 git 状态，给低分 agent 写清下一步小切片、测试和 PR 要求。",
            "- 每轮必须关闭至少一个调度闭环：dirty/ahead 收口、PR 推进、失败检查分派、提示词修正或权威复采样。",
            "- 每轮 final 必须列出所有 managed agent 的 dirty/ahead/behind、最新日志更新时间、open PR 和下一步强制动作。",
            "- 监督周期内必须主动推进交付闭环：发现 agent dirty/ahead、PR 堆积、检查失败、长日志或状态不一致时，先派发/调整对应 agent 去提交、推送、开 PR、修复或复采样。",
            "- 若 15 分钟摘要和 systemd 实际 unit 不一致，优先修正 manager 采样与状态文件，不允许邮件继续使用旧摘要。",
            "- 可以修改 docs/ops 的 manager、邮件、提示词和队列逻辑；业务修复必须分派给对应 owning agent 或单独 fix agent。",
            "- 合并或推动合并 PR 后，必须立即运行正常 manager 复采样，刷新 summary/actions/mail 输入，避免已合并 PR 继续出现在下一步行动里。",
            "- 只按 agent 身份管理，禁止恢复旧 scope/路径分片模型。",
        ],
    }
    return "\n".join(common + specific.get(agent_id, []))


def shell_export(name: str, value: str) -> str:
    return f"export {name}={shlex.quote(value)}"


def persona_text(agent_id: str, agent: dict[str, Any], workdir: Path, key_alias: str) -> str:
    docs = "\n".join(f"- `/root/gotouhou/{item}`" for item in agent.get("docs", ()))
    checks = "\n".join(f"- `{item}`" for item in agent.get("checks", ()))
    limits = agent_operating_limits(agent_id)
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

## 运行约束

{limits}

## 必读文档

{docs}

## 验证优先级

{checks}

## 特别边界

- Godot 服务器无显卡导致的纯 renderer/RenderingDevice 失败可记录为环境 blocked；GDScript parse/compile/type error、脚本加载失败、UI/弹幕合同失败必须修复。
- 服务端使用 `docker-compose` 命令，不使用 `docker compose`。
- 涉及协议、网络、匹配、战斗服、鉴权或安全边界时必须运行 `/root/gotouhou/docs/ops/protocol_audit_check.py`。
"""


def prompt_clip(value: object, max_chars: int = PROMPT_MAX_TEXT_CHARS) -> str:
    text = str(value or "").replace("\n", " ").strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def previous_next_action_prompt(agent_id: str, previous: dict[str, Any]) -> str:
    next_actions = previous.get("next_agent_actions") if isinstance(previous.get("next_agent_actions"), dict) else {}
    items = next_actions.get("items") if isinstance(next_actions.get("items"), list) else []
    matching_items: list[dict[str, Any]] = []
    for raw_item in items:
        item = raw_item if isinstance(raw_item, dict) else {}
        if item.get("agent") != agent_id:
            continue
        matching_items.append(item)

    lines: list[str] = []
    resource_items = [
        item
        for item in matching_items
        if item.get("category") == "resource_risk" and " low resource risk" not in str(item.get("summary") or "")
    ]
    work_items = [item for item in matching_items if item.get("category") != "resource_risk"]

    for item in resource_items[:PROMPT_MAX_RESOURCE_ACTION_LINES]:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        reasons = evidence.get("reasons") if isinstance(evidence.get("reasons"), list) else []
        reason_text = prompt_clip(",".join(str(reason) for reason in reasons[:3]), 96)
        reason_suffix = f" reasons={reason_text}" if reason_text else ""
        lines.append(
            "- "
            f"resource_limit priority={item.get('priority')} severity={prompt_clip(str(item.get('summary') or '').replace(agent_id + ' ', ''), 80)} "
            f"repo={prompt_clip(item.get('repo'), 64)} action={prompt_clip(item.get('action'))}{reason_suffix}"
        )

    for item in work_items:
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        url = evidence.get("url")
        url_text = f" {prompt_clip(url, 140)}" if url else ""
        lines.append(
            "- "
            f"priority={item.get('priority')} category={item.get('category')} "
            f"repo={prompt_clip(item.get('repo'), 64)} action={prompt_clip(item.get('action'))} "
            f"summary={prompt_clip(item.get('summary'))}{url_text}"
        )
        if len(lines) >= PROMPT_MAX_NEXT_ACTION_LINES:
            break
    if not lines:
        return "- 当前没有 manager 写入的结构化下一步行动项；按 docs/dev 和当前仓库状态选择最小切片。"
    return "\n".join(lines)


def repo_state_prompt_action(item: dict[str, Any]) -> str:
    category = str(item.get("category") or "")
    repo = prompt_clip(item.get("repo"), 64)
    evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
    branch = prompt_clip(evidence.get("branch"), 96)
    dirty_count = evidence.get("dirty_count")
    if category == "dirty_worktree":
        dirty_suffix = f"dirty={dirty_count}；" if dirty_count is not None else ""
        return (
            f"先止血版本状态：检查 {repo} {branch} 的 {dirty_suffix}"
            "只做保留价值判断，提交/推 PR 或写明 supersede/废弃原因；完成前不要扩展新业务切片"
        )
    if category == "legacy_branch_checkout":
        return (
            f"不要把 {repo} root checkout 的 legacy 分支 {branch} 当基线；"
            "如有价值先迁移到 owning managed agent branch，否则只记录清退说明"
        )
    if category == "local_ahead":
        ahead = evidence.get("ahead")
        return (
            f"先处理 {repo} {branch} 本地 ahead={ahead}：推送并开/更新 PR，"
            "或记录无法推送原因；不要继续叠加本地提交"
        )
    if category == "local_behind":
        behind = evidence.get("behind")
        return f"先同步 {repo} {branch} behind={behind} 到最新 upstream，再选择新切片"
    return str(item.get("action") or "inspect repository state")


def managed_worktree_action(agent_id: str, agent: dict[str, Any], category: str, worktree_state: dict[str, Any]) -> dict[str, Any]:
    repo = str(agent.get("repo") or AGENTS.get(agent_id, {}).get("repo") or "unknown")
    branch = str(worktree_state.get("branch") or "")
    evidence = {
        "path": worktree_state.get("path"),
        "branch": branch,
        "head": worktree_state.get("head"),
        "dirty_count": worktree_state.get("dirty_count"),
        "dirty": worktree_state.get("dirty"),
        "ahead": worktree_state.get("ahead"),
        "behind": worktree_state.get("behind"),
        "status": worktree_state.get("status"),
    }
    if category == "managed_worktree_dirty":
        dirty_count = int(worktree_state.get("dirty_count", 0) or 0)
        return {
            "agent": agent_id,
            "repo": repo,
            "priority": 6,
            "category": category,
            "summary": f"{agent_id} managed worktree has dirty={dirty_count} on {branch}",
            "action": "先收敛当前代码切片：运行相关检查，提交 scoped 改动，推送/开 PR 或写明阻塞；完成前不要继续扩展新功能",
            "evidence": evidence,
        }
    if category == "managed_worktree_ahead":
        ahead = int(worktree_state.get("ahead", 0) or 0)
        return {
            "agent": agent_id,
            "repo": repo,
            "priority": 7,
            "category": category,
            "summary": f"{agent_id} managed worktree is ahead={ahead} on {branch}",
            "action": "先推送 ahead 提交并开/更新 PR，或写明无法推送原因；不要继续堆 only-local 提交",
            "evidence": evidence,
        }
    behind = int(worktree_state.get("behind", 0) or 0)
    return {
        "agent": agent_id,
        "repo": repo,
        "priority": 28,
        "category": category,
        "summary": f"{agent_id} managed worktree is behind={behind} on {branch}",
        "action": "先同步最新 upstream/main 或 owning branch，再继续新切片",
        "evidence": evidence,
    }


def previous_health_prompt(agent_id: str, previous: dict[str, Any]) -> str:
    health = previous.get("agent_health") if isinstance(previous.get("agent_health"), dict) else {}
    agents = health.get("agents") if isinstance(health.get("agents"), dict) else {}
    item = agents.get(agent_id) if isinstance(agents.get(agent_id), dict) else {}
    if not item:
        return "- 尚无上一轮健康评分；本轮按 docs/dev 和当前仓库状态建立基线。"
    reasons = item.get("reasons") if isinstance(item.get("reasons"), list) else []
    actions = item.get("actions") if isinstance(item.get("actions"), list) else []
    reason_text = "；".join(prompt_clip(reason, 120) for reason in reasons[:4]) or "无扣分原因"
    action_text = "；".join(prompt_clip(action, 120) for action in actions[:4]) or "继续推进最小可验证切片"
    return (
        "- "
        f"score={item.get('score', 'unknown')} label={item.get('label', 'unknown')}；"
        f"扣分/状态：{reason_text}；建议动作：{action_text}"
    )


def agent_prompt(agent_id: str, agent: dict[str, Any], persona_path: Path, workdir: Path, key_assignment: dict[str, Any], previous: dict[str, Any]) -> str:
    return f"""你现在是 `{agent_id}`，必须按 Codex `/goal` 持续目标模式工作。

先完整阅读人格文档：`{persona_path}`。

当前独立工作环境：`{workdir}`
工作区总根目录：`/root/gotouhou`
Key alias：`{key_assignment.get("alias") or "(missing)"}`。原始 key 只由 runner 注入环境，禁止打印、写入日志、邮件或 git。

本轮目标：
{agent["mission"]}

Manager 下一步行动提示：
{previous_next_action_prompt(agent_id, previous)}

上一轮推进健康评分：
{previous_health_prompt(agent_id, previous)}

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


def current_log_path(root: Path, agent_id: str, lock: dict[str, Any]) -> Path | None:
    """Prefer the live run's log path so a fresh restart is not scored from old logs."""
    raw_path = lock.get("log_path") if isinstance(lock, dict) else None
    if lock.get("alive") and isinstance(raw_path, str) and raw_path:
        path = Path(raw_path)
        return path
    return latest_log(root, agent_id)


def read_log_sample(path: Path, max_bytes: int = LOG_SAMPLE_BYTES) -> tuple[str, int, bool]:
    stat = path.stat()
    sample_bytes = min(stat.st_size, max_bytes)
    with path.open("rb") as handle:
        if stat.st_size > sample_bytes:
            handle.seek(-sample_bytes, os.SEEK_END)
        data = handle.read(sample_bytes)
    return data.decode("utf-8", errors="replace"), sample_bytes, stat.st_size > sample_bytes


def log_info(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {"exists": False}
    if not path.exists():
        return {"exists": False, "path": str(path), "pending_create": True}
    stat = path.stat()
    text, sampled_bytes, tail_truncated = read_log_sample(path)
    exit_status = None
    for match in re.finditer(r"^\[goal-manager\] exited status=(\d+)\s*$", text, flags=re.MULTILINE):
        exit_status = int(match.group(1))
    token_usage = None
    token_matches = list(re.finditer(r"tokens used\s*\n\s*([0-9,]+)", text, flags=re.IGNORECASE))
    if token_matches:
        token_usage = int(token_matches[-1].group(1).replace(",", ""))
    return {
        "exists": True,
        "path": str(path),
        "updated_at": iso(dt.datetime.fromtimestamp(stat.st_mtime, UTC)),
        "bytes": stat.st_size,
        "sampled_bytes": sampled_bytes,
        "tail_truncated": tail_truncated,
        "line_count": text.count("\n") + (1 if text else 0) if not tail_truncated else None,
        "sampled_line_count": text.count("\n") + (1 if text else 0),
        "exited": exit_status is not None,
        "exit_status": exit_status,
        "token_usage": token_usage,
        "tail": text[-LOG_TAIL_CHARS:],
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


def collect_git_worktree_state(path: Path) -> dict[str, Any]:
    if not (path / ".git").exists():
        return {"path": str(path), "missing": True}
    branch = run_command(["git", "branch", "--show-current"], path)[1]
    head = run_command(["git", "rev-parse", "--short", "HEAD"], path)[1]
    status = run_command(["git", "status", "--short", "--branch"], path)[1]
    dirty = [line for line in status.splitlines() if line and not line.startswith("## ")]
    branch_info = repo_status_branch_info(status)
    return {
        "path": str(path),
        "missing": False,
        "branch": branch,
        "head": head,
        "status": status,
        "dirty_count": len(dirty),
        "dirty": dirty[:20],
        "ahead": int(branch_info.get("ahead", 0) or 0),
        "behind": int(branch_info.get("behind", 0) or 0),
        "tracking": branch_info.get("tracking"),
        "diverged": bool(branch_info.get("diverged")),
    }


def repo_owner_agent(repo_name: str, branch: object = "") -> str:
    branch_name = str(branch or "")
    if repo_name == "SpellKard":
        return "client-agent"
    if repo_name == "Gensoulkyo":
        return "nakama-server-agent"
    if repo_name == "PhK-BattleServer":
        return "battle-server-agent"
    if repo_name == "PhK-Protocol":
        return "audit-agent"
    if repo_name == "docs":
        if "audit-agent" in branch_name:
            return "audit-agent"
        return "project-manager-agent"
    return "project-manager-agent"


def repo_status_branch_info(status: object) -> dict[str, Any]:
    lines = str(status or "").splitlines()
    header = next((line for line in lines if line.startswith("## ")), "")
    info: dict[str, Any] = {
        "header": header,
        "tracking": "",
        "ahead": 0,
        "behind": 0,
        "diverged": False,
    }
    if not header:
        return info
    branch_text = header[3:]
    status_match = re.search(r"\[([^\]]+)\]", branch_text)
    if "..." in branch_text:
        info["tracking"] = branch_text.split("...", 1)[1].split(" [", 1)[0].strip()
    if not status_match:
        return info
    for part in (piece.strip() for piece in status_match.group(1).split(",")):
        ahead_match = re.search(r"ahead\s+(\d+)", part)
        behind_match = re.search(r"behind\s+(\d+)", part)
        if ahead_match:
            info["ahead"] = int(ahead_match.group(1))
        if behind_match:
            info["behind"] = int(behind_match.group(1))
    info["diverged"] = bool(info["ahead"] and info["behind"])
    return info


def expected_repo_branches(repo_name: str) -> set[str]:
    branches = {str(agent.get("branch") or "") for agent in AGENTS.values() if agent.get("repo") == repo_name}
    branches.discard("")
    branches.add("main")
    return branches


def build_repo_state_risk(repos: dict[str, Any]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    by_repo: dict[str, int] = {}
    by_agent: dict[str, int] = {}
    by_category: dict[str, int] = {}

    for repo_name, raw_repo in sorted(repos.items()):
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        if repo.get("missing"):
            owner = repo_owner_agent(repo_name)
            items.append(
                {
                    "repo": repo_name,
                    "owner_agent": owner,
                    "priority": 12,
                    "category": "repo_missing",
                    "summary": f"{repo_name} repository missing at {repo.get('path')}",
                    "action": "restore the repository checkout before scheduling work",
                    "evidence": {"path": repo.get("path")},
                }
            )
            continue

        branch = str(repo.get("branch") or "")
        owner = repo_owner_agent(repo_name, branch)
        dirty_count = int(repo.get("dirty_count", 0) or 0)
        branch_info = repo_status_branch_info(repo.get("status"))
        ahead = int(branch_info.get("ahead", 0) or 0)
        behind = int(branch_info.get("behind", 0) or 0)
        expected_branches = expected_repo_branches(repo_name)

        if dirty_count:
            priority = 8 if repo_name in {"Gensoulkyo", "PhK-BattleServer", "PhK-Protocol"} else 18
            items.append(
                {
                    "repo": repo_name,
                    "owner_agent": owner,
                    "priority": priority,
                    "category": "dirty_worktree",
                    "summary": f"{repo_name} has {dirty_count} uncommitted item(s) on {branch}",
                    "action": "inspect the dirty work, preserve useful changes in a small commit/PR, or document explicit discard/supersede",
                    "evidence": {
                        "branch": branch,
                        "head": repo.get("head"),
                        "dirty_count": dirty_count,
                        "dirty": repo.get("dirty"),
                    },
                }
            )

        if ahead:
            items.append(
                {
                    "repo": repo_name,
                    "owner_agent": owner,
                    "priority": 16 if repo_name == "SpellKard" else 45,
                    "category": "local_ahead",
                    "summary": f"{repo_name} {branch} is ahead of upstream by {ahead} commit(s)",
                    "action": "push or convert the local commits into a current-base PR, then sync the owning managed branch",
                    "evidence": {
                        "branch": branch,
                        "head": repo.get("head"),
                        "status_header": branch_info.get("header"),
                        "ahead": ahead,
                        "behind": behind,
                    },
                }
            )

        if behind:
            items.append(
                {
                    "repo": repo_name,
                    "owner_agent": owner,
                    "priority": 50,
                    "category": "local_behind",
                    "summary": f"{repo_name} {branch} is behind upstream by {behind} commit(s)",
                    "action": "update the checkout before using it as a baseline for new work",
                    "evidence": {
                        "branch": branch,
                        "head": repo.get("head"),
                        "status_header": branch_info.get("header"),
                        "ahead": ahead,
                        "behind": behind,
                    },
                }
            )

        if branch and branch not in expected_branches and branch.startswith("agent/"):
            items.append(
                {
                    "repo": repo_name,
                    "owner_agent": owner,
                    "priority": 65,
                    "category": "legacy_branch_checkout",
                    "summary": f"{repo_name} root checkout is on legacy/non-managed branch {branch}",
                    "action": "avoid using this root checkout as the canonical baseline; migrate any useful work into the owning managed agent branch",
                    "evidence": {
                        "branch": branch,
                        "head": repo.get("head"),
                        "expected_branches": sorted(expected_branches),
                    },
                }
            )

    items.sort(key=lambda item: (int(item.get("priority", 99) or 99), str(item.get("repo", "")), str(item.get("category", ""))))
    for item in items:
        repo = str(item.get("repo") or "unknown")
        owner = str(item.get("owner_agent") or "unknown")
        category = str(item.get("category") or "unknown")
        by_repo[repo] = by_repo.get(repo, 0) + 1
        by_agent[owner] = by_agent.get(owner, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "count": len(items),
        "by_repo": by_repo,
        "by_owner_agent": by_agent,
        "by_category": by_category,
        "items": items,
        "top_items": items[:10],
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


def review_gate_detail(review_gate: dict[str, Any]) -> str:
    if not review_gate.get("required"):
        return ""
    category = str(review_gate.get("category") or "review")
    reason = str(review_gate.get("reason") or "").strip()
    return f" review_gate={category}" + (f":{reason}" if reason else "")


def pull_request_owner_agent(repo_name: str, head_ref: object) -> str:
    head = str(head_ref or "")
    if repo_name == "docs":
        if "audit-agent" in head:
            return "audit-agent"
        if "project-manager-agent" in head:
            return "project-manager-agent"
    return repo_owner_agent(repo_name, head)


def merge_review_gate(repo_name: str, item: dict[str, Any]) -> dict[str, Any]:
    """Describe merge-review gates that cannot be inferred from check state."""
    title = str(item.get("title") or "").lower()
    head = str(item.get("headRefName") or "").lower()
    haystack = f"{repo_name.lower()} {title} {head}"
    security_terms = (
        "protocol",
        "network",
        "security",
        "auth",
        "ticket",
        "settlement",
        "callback",
        "envelope",
        "battle",
        "boss",
        "kcp",
        "aead",
        "crypto",
    )
    if repo_name in {"Gensoulkyo", "PhK-BattleServer", "PhK-Protocol"}:
        return {
            "required": True,
            "category": "protocol_network_security",
            "reason": "server/protocol repository changes need diff review and protocol-audit evidence before merge",
        }
    if any(term in haystack for term in security_terms):
        return {
            "required": True,
            "category": "protocol_network_security",
            "reason": "PR title or branch touches protocol/network/security-sensitive areas",
        }
    return {"required": False, "category": "standard", "reason": ""}


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
    if checks.get("pending", 0) > 0:
        return 30, "wait_checks", "wait for pending checks"
    if merge_state in {"BLOCKED", "HAS_HOOKS"}:
        return 40, "blocked_gate", "wait for required review/check gates or branch protection"
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
            review_gate = merge_review_gate(repo_name, item)
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
                    "review_gate": review_gate,
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


def write_personas(root: Path, agent_id: str, agent: dict[str, Any], workdir: Path, key_assignment: dict[str, Any], previous: dict[str, Any]) -> dict[str, str]:
    persona_dir = root / ".agents" / "personas"
    prompt_dir = root / ".agents" / "agent-prompts"
    workspace_dir = root / ".agents" / "workspaces" / agent_id
    persona_path = persona_dir / f"{agent_id}.md"
    prompt_path = prompt_dir / f"{agent_id}.md"
    readme_path = workspace_dir / "README.md"
    key_alias = str(key_assignment.get("alias") or "")
    atomic_write_text(persona_path, persona_text(agent_id, agent, workdir, key_alias))
    atomic_write_text(prompt_path, agent_prompt(agent_id, agent, persona_path, workdir, key_assignment, previous))
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


def refresh_personas_from_summary(root: Path, summary: dict[str, Any]) -> None:
    """Refresh prompts with the just-built action queue when no new agent was started."""
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    for agent_id, agent in AGENTS.items():
        raw_state = agents.get(agent_id) if isinstance(agents.get(agent_id), dict) else {}
        workdir = Path(str(raw_state.get("workdir") or root / str(agent.get("repo", ""))))
        key_assignment = {
            "alias": raw_state.get("key_alias"),
            "available": raw_state.get("key_available"),
            "preferences": agent.get("key_aliases", ()),
        }
        write_personas(root, agent_id, agent, workdir, key_assignment, summary)


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
        "log_path": payload.get("log_path") if isinstance(payload, dict) else None,
        "runner_path": payload.get("runner_path") if isinstance(payload, dict) else None,
        "prompt_path": payload.get("prompt_path") if isinstance(payload, dict) else None,
        "cwd": payload.get("cwd") if isinstance(payload, dict) else None,
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
        return {"started": False, "reason": "read-only-sample", "would_start": True, "key_alias": key_alias}
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
    log_prefixes: dict[str, dict[str, Any]] = {}
    logs_dir = root / ".agents" / "logs"
    if logs_dir.exists():
        for path in logs_dir.glob("*.log"):
            match = re.match(r"(.+)-\d{8}T\d{6}Z\.log$", path.name)
            if not match:
                continue
            prefix = match.group(1)
            if prefix in MANAGED_AGENT_IDS:
                continue
            stat = path.stat()
            record = log_prefixes.setdefault(
                prefix,
                {"prefix": prefix, "count": 0, "latest_log": "", "latest_updated_at": "", "latest_bytes": 0},
            )
            record["count"] = int(record["count"]) + 1
            latest_dt = parse_iso(record.get("latest_updated_at"))
            updated_at = dt.datetime.fromtimestamp(stat.st_mtime, UTC)
            if latest_dt is None or updated_at > latest_dt:
                record["latest_log"] = str(path)
                record["latest_updated_at"] = iso(updated_at)
                record["latest_bytes"] = stat.st_size
    return {
        "systemd_status": code,
        "systemd_units": units.splitlines()[:80],
        "old_roster_records": old_records,
        "old_roster_record_count": len(old_records),
        "legacy_log_prefixes": sorted(log_prefixes.values(), key=lambda item: str(item.get("prefix", ""))),
        "legacy_log_prefix_count": len(log_prefixes),
    }


def build_agent_resource_risk(
    agents: dict[str, Any],
    legacy: dict[str, Any],
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    sample_time = now or utcnow()
    items: list[dict[str, Any]] = []
    for agent_id, raw_agent in sorted(agents.items()):
        agent = raw_agent if isinstance(raw_agent, dict) else {}
        runtime_log = agent.get("runtime_log") if isinstance(agent.get("runtime_log"), dict) else {}
        token_usage = runtime_log.get("token_usage")
        log_bytes = int(runtime_log.get("bytes", 0) or 0)
        updated_at = parse_iso(runtime_log.get("updated_at"))
        log_age_seconds = max(0, int((sample_time - updated_at).total_seconds())) if updated_at else None
        severity = "low"
        reasons: list[str] = []
        action = "keep normal slice size"

        if agent.get("status") == "running" and log_age_seconds is not None:
            if log_age_seconds >= RUNNING_LOG_STALE_HIGH_SECONDS:
                severity = "high"
                reasons.append(f"running_log_stale_seconds>={RUNNING_LOG_STALE_HIGH_SECONDS}")
                action = "立即检查该 agent 是否卡在测试/网络/权限；把下一轮压缩为提交、推送、PR 或明确阻塞"
            elif log_age_seconds >= RUNNING_LOG_STALE_MEDIUM_SECONDS:
                severity = "medium"
                reasons.append(f"running_log_stale_seconds>={RUNNING_LOG_STALE_MEDIUM_SECONDS}")
                action = "下轮优先要求该 agent 收敛当前小切片并刷新 final/status，不继续扩展任务"

        if isinstance(token_usage, int):
            if token_usage >= TOKEN_HIGH_RISK:
                severity = "high"
                reasons.append(f"last_run_tokens>={TOKEN_HIGH_RISK}")
                action = "把下一轮切成更小的 PR-ready 切片，final 只写结论、提交/PR、测试和阻塞"
            elif token_usage >= TOKEN_MEDIUM_RISK:
                if severity == "low":
                    severity = "medium"
                reasons.append(f"last_run_tokens>={TOKEN_MEDIUM_RISK}")
                action = "缩短下一轮任务，先提交/推送已验证成果再扩展"
        elif agent.get("status") == "running":
            reasons.append("running_without_final_token_sample")

        if log_bytes >= LOG_BYTES_HIGH_RISK:
            severity = "high"
            reasons.append(f"log_bytes>={LOG_BYTES_HIGH_RISK}")
            action = "停止复制长日志；只汇总检查结果、PR 状态和关键错误"
        elif log_bytes >= LOG_BYTES_MEDIUM_RISK and severity == "low":
            severity = "medium"
            reasons.append(f"log_bytes>={LOG_BYTES_MEDIUM_RISK}")
            action = "压缩报告和日志尾部，优先写结构化状态字段"

        if not reasons:
            reasons.append("within_current_thresholds")
        items.append(
            {
                "agent": agent_id,
                "repo": agent.get("repo"),
                "status": agent.get("status"),
                "severity": severity,
                "token_usage": token_usage,
                "log_bytes": log_bytes,
                "log_age_seconds": log_age_seconds,
                "reasons": reasons,
                "action": action,
            }
        )

    old_records = legacy.get("old_roster_records") if isinstance(legacy.get("old_roster_records"), list) else []
    legacy_prefixes = legacy.get("legacy_log_prefixes") if isinstance(legacy.get("legacy_log_prefixes"), list) else []
    if old_records or legacy_prefixes:
        items.append(
            {
                "agent": "legacy-agent-roster",
                "repo": "ops",
                "status": "frozen",
                "severity": "medium",
                "token_usage": None,
                "log_bytes": 0,
                "reasons": [f"old_roster_records={len(old_records)}", f"legacy_log_prefixes={len(legacy_prefixes)}"],
                "action": "keep old agents frozen; only migrate proven useful work into the five managed agents",
            }
        )

    severity_order = {"high": 0, "medium": 1, "low": 2}
    items.sort(key=lambda item: (severity_order.get(str(item.get("severity")), 9), str(item.get("agent", ""))))
    legacy_items = [item for item in items if item.get("agent") == "legacy-agent-roster"]
    managed_items = [item for item in items if item.get("agent") != "legacy-agent-roster"]
    return {
        "thresholds": {
            "token_medium": TOKEN_MEDIUM_RISK,
            "token_high": TOKEN_HIGH_RISK,
            "log_bytes_medium": LOG_BYTES_MEDIUM_RISK,
            "log_bytes_high": LOG_BYTES_HIGH_RISK,
            "running_log_stale_medium_seconds": RUNNING_LOG_STALE_MEDIUM_SECONDS,
            "running_log_stale_high_seconds": RUNNING_LOG_STALE_HIGH_SECONDS,
        },
        "high_count": sum(1 for item in managed_items if item.get("severity") == "high"),
        "medium_count": sum(1 for item in managed_items if item.get("severity") == "medium"),
        "legacy_count": len(legacy_items),
        "legacy_items": legacy_items,
        "items": items,
        "top_items": managed_items[:8],
    }


def build_next_agent_actions(
    pull_request_queue: dict[str, Any],
    resource_risk: dict[str, Any],
    repo_state_risk: dict[str, Any],
    agents: dict[str, Any] | None = None,
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []

    for agent_id, raw_agent in sorted((agents or {}).items()):
        agent = raw_agent if isinstance(raw_agent, dict) else {}
        worktree_state = agent.get("worktree_state") if isinstance(agent.get("worktree_state"), dict) else {}
        if not worktree_state or worktree_state.get("missing"):
            continue
        if int(worktree_state.get("dirty_count", 0) or 0) > 0:
            items.append(managed_worktree_action(agent_id, agent, "managed_worktree_dirty", worktree_state))
        if int(worktree_state.get("ahead", 0) or 0) > 0:
            items.append(managed_worktree_action(agent_id, agent, "managed_worktree_ahead", worktree_state))
        if int(worktree_state.get("behind", 0) or 0) > 0:
            items.append(managed_worktree_action(agent_id, agent, "managed_worktree_behind", worktree_state))

    for raw_item in repo_state_risk.get("top_items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        items.append(
            {
                "agent": str(item.get("owner_agent") or "project-manager-agent"),
                "repo": str(item.get("repo") or "unknown"),
                "priority": int(item.get("priority", 40) or 40),
                "category": str(item.get("category") or "repo_state"),
                "summary": str(item.get("summary") or ""),
                "action": repo_state_prompt_action(item),
                "evidence": item.get("evidence") if isinstance(item.get("evidence"), dict) else {},
            }
        )

    for raw_group in pull_request_queue.get("supersede_groups", []):
        group = raw_group if isinstance(raw_group, dict) else {}
        repo = str(group.get("repo") or "unknown")
        owner = str(group.get("owner_agent") or "project-manager-agent")
        items.append(
            {
                "agent": owner,
                "repo": repo,
                "priority": 5,
                "category": "pr_supersede_group",
                "summary": f"{repo} stale PR group count={group.get('count')} prs={group.get('numbers')}",
                "action": str(group.get("action") or "consolidate stale pull requests"),
                "evidence": {
                    "numbers": group.get("numbers"),
                    "merge_states": group.get("merge_states"),
                    "action_categories": group.get("action_categories"),
                },
            }
        )

    for raw_item in pull_request_queue.get("top_items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        category = str(item.get("action_category") or "")
        if category not in {"resolve_conflicts", "update_branch", "fix_checks", "wait_checks", "blocked_gate", "inspect"}:
            continue
        repo = str(item.get("repo") or "unknown")
        items.append(
            {
                "agent": str(item.get("owner_agent") or "project-manager-agent"),
                "repo": repo,
                "priority": int(item.get("priority", 50) or 50),
                "category": category,
                "summary": f"{repo} #{item.get('number')} {item.get('merge_state')} {item.get('title')}",
                "action": str(item.get("action") or "inspect pull request"),
                "evidence": {"url": item.get("url"), "checks": item.get("checks"), "head": item.get("head")},
            }
        )

    for raw_item in pull_request_queue.get("merge_ready_items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        gate = item.get("review_gate") if isinstance(item.get("review_gate"), dict) else {}
        repo = str(item.get("repo") or "unknown")
        if gate.get("required"):
            priority = 35
            category = str(gate.get("category") or "review_gate")
            action = "diff-review the PR, verify protocol/security evidence, then merge or request fixes"
        else:
            priority = 55
            category = "merge_ready_review"
            action = "final review, merge, and sync the owning persistent branch"
        items.append(
            {
                "agent": str(item.get("owner_agent") or "project-manager-agent"),
                "repo": repo,
                "priority": priority,
                "category": category,
                "summary": f"{repo} #{item.get('number')} merge-ready {item.get('title')}",
                "action": action,
                "evidence": {"url": item.get("url"), "checks": item.get("checks"), "review_gate": gate},
            }
        )

    for raw_item in resource_risk.get("top_items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        agent = str(item.get("agent") or "")
        if not agent or agent == "legacy-agent-roster":
            continue
        severity = str(item.get("severity") or "low")
        if severity == "low":
            continue
        items.append(
            {
                "agent": agent,
                "repo": str(item.get("repo") or "unknown"),
                "priority": 80 if severity == "high" else 90,
                "category": "resource_risk",
                "summary": f"{agent} {severity} resource risk",
                "action": str(item.get("action") or "keep the next iteration small"),
                "evidence": {
                    "token_usage": item.get("token_usage"),
                    "log_bytes": item.get("log_bytes"),
                    "reasons": item.get("reasons"),
                },
            }
        )

    items.sort(
        key=lambda item: (
            int(item.get("priority", 99) or 99),
            str(item.get("agent") or ""),
            str(item.get("repo") or ""),
            str(item.get("summary") or ""),
        )
    )
    by_agent: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for item in items:
        agent = str(item.get("agent") or "unknown")
        category = str(item.get("category") or "unknown")
        by_agent[agent] = by_agent.get(agent, 0) + 1
        by_category[category] = by_category.get(category, 0) + 1
    return {
        "count": len(items),
        "by_agent": by_agent,
        "by_category": by_category,
        "items": items,
        "top_items": items[:10],
    }


def health_label(score: int) -> str:
    if score >= 85:
        return "healthy"
    if score >= 70:
        return "watch"
    if score >= 50:
        return "needs_correction"
    return "blocked"


def build_agent_health(
    agents: dict[str, Any],
    repo_state_risk: dict[str, Any],
    pull_request_queue: dict[str, Any],
    resource_risk: dict[str, Any],
    next_actions: dict[str, Any],
) -> dict[str, Any]:
    """Score each sustained agent so the manager can steer without scope heuristics."""
    repo_items_by_agent: dict[str, list[dict[str, Any]]] = {}
    for raw_item in repo_state_risk.get("items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        owner = str(item.get("owner_agent") or "")
        if owner:
            repo_items_by_agent.setdefault(owner, []).append(item)

    pr_items_by_agent: dict[str, list[dict[str, Any]]] = {}
    for raw_item in pull_request_queue.get("items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        owner = str(item.get("owner_agent") or "")
        if owner:
            pr_items_by_agent.setdefault(owner, []).append(item)

    resource_by_agent: dict[str, dict[str, Any]] = {}
    for raw_item in resource_risk.get("items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        agent = str(item.get("agent") or "")
        if agent:
            resource_by_agent[agent] = item

    next_by_agent: dict[str, list[dict[str, Any]]] = {}
    for raw_item in next_actions.get("items", []):
        item = raw_item if isinstance(raw_item, dict) else {}
        agent = str(item.get("agent") or "")
        if agent:
            next_by_agent.setdefault(agent, []).append(item)

    scored: dict[str, Any] = {}
    for agent_id in MANAGED_AGENT_IDS:
        raw_agent = agents.get(agent_id) if isinstance(agents.get(agent_id), dict) else {}
        status = str(raw_agent.get("status") or "unknown")
        score = 100
        reasons: list[str] = []
        actions: list[str] = []

        if status == "running":
            reasons.append("goal agent 正在运行")
        elif status == "completed":
            score -= 8
            reasons.append("agent 正常退出，持续目标需要 supervisor 继续拉起")
            actions.append("等待 15 分钟 supervisor 或手动触发 manager 补启")
        elif status in {"failed", "stopped"}:
            score -= 35
            reasons.append(f"agent 状态为 {status}")
            actions.append("检查 runtime log，修复失败后补启")
        else:
            score -= 25
            reasons.append(f"agent 状态未知或缺失：{status}")
            actions.append("由 manager 补启缺失 agent")

        if not raw_agent.get("key_available", True):
            score -= 30
            reasons.append("缺少可用 key alias")
            actions.append("修复 /root/.codex/keys 中该 agent 的 alias")

        if not raw_agent.get("progress"):
            score -= 10
            reasons.append("本轮未记录 progress 信号")
            actions.append("下一轮必须写 final、commit/PR、测试或阻塞说明")

        worktree_state = raw_agent.get("worktree_state") if isinstance(raw_agent.get("worktree_state"), dict) else {}
        if worktree_state.get("missing"):
            score -= 15
            reasons.append("agent worktree 不存在或不是 git 仓库")
            actions.append("修复 agent 独立 worktree 后再继续")
        else:
            dirty_count = int(worktree_state.get("dirty_count", 0) or 0)
            ahead = int(worktree_state.get("ahead", 0) or 0)
            behind = int(worktree_state.get("behind", 0) or 0)
            if dirty_count:
                score -= min(12, 4 + dirty_count)
                reasons.append(f"agent worktree dirty={dirty_count}")
                actions.append("先整理 worktree dirty：提交、开 PR、或记录明确废弃理由")
            if ahead:
                score -= 15 if ahead >= 5 else 8
                reasons.append(f"agent worktree ahead={ahead}")
                actions.append("推送 ahead 提交并开/更新 PR，或在 final 写明无法推送原因")
            if behind:
                score -= 6
                reasons.append(f"agent worktree behind={behind}")
                actions.append("同步最新 origin/main 或对应 managed branch 后再扩展功能")

        resource = resource_by_agent.get(agent_id, {})
        severity = str(resource.get("severity") or "low")
        if severity == "high":
            score -= 15
            reasons.append("资源风险 high")
            actions.append(str(resource.get("action") or "缩小下一轮任务"))
        elif severity == "medium":
            score -= 8
            reasons.append("资源风险 medium")
            actions.append(str(resource.get("action") or "缩短下一轮任务并先提交"))

        repo_penalty = 0
        for item in repo_items_by_agent.get(agent_id, [])[:4]:
            priority = int(item.get("priority", 50) or 50)
            if priority <= 10:
                repo_penalty += 12
            elif priority <= 20:
                repo_penalty += 8
            else:
                repo_penalty += 4
            reasons.append(f"仓库风险：{item.get('category')} {item.get('repo')}")
            actions.append(repo_state_prompt_action(item))
        score -= min(repo_penalty, 20)

        pr_penalty = 0
        for item in pr_items_by_agent.get(agent_id, [])[:4]:
            category = str(item.get("action_category") or "")
            if category in {"resolve_conflicts", "fix_checks"}:
                pr_penalty += 10
            elif category == "update_branch":
                pr_penalty += 7
            elif category in {"blocked_gate", "inspect"}:
                pr_penalty += 4
            elif category == "wait_checks":
                pr_penalty += 2
            elif category == "merge_ready":
                pr_penalty += 1
            if category:
                reasons.append(f"PR 队列：{item.get('repo')} #{item.get('number')} {category}")
                actions.append(str(item.get("action") or "处理 PR 队列"))
        score -= min(pr_penalty, 20)

        for item in next_by_agent.get(agent_id, [])[:3]:
            action = str(item.get("action") or "").strip()
            if action and action not in actions:
                actions.append(action)

        score = max(0, min(100, score))
        scored[agent_id] = {
            "agent": agent_id,
            "repo": raw_agent.get("repo") or AGENTS[agent_id]["repo"],
            "status": status,
            "worktree_state": worktree_state,
            "score": score,
            "label": health_label(score),
            "reasons": reasons[:8],
            "actions": actions[:8],
        }

    average = round(sum(int(item["score"]) for item in scored.values()) / max(1, len(scored)))
    low_score_agents = [agent_id for agent_id, item in scored.items() if int(item.get("score", 0) or 0) < 70]
    return {
        "model": "goal-agent-status-version-resource-pr-v1",
        "score": average,
        "label": health_label(average),
        "average_score": average,
        "low_score_threshold": 70,
        "low_score_agents": low_score_agents,
        "agents": scored,
    }


def build_audit_report(summary: dict[str, Any]) -> str:
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    repos = summary.get("repos") if isinstance(summary.get("repos"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    legacy = summary.get("legacy_agents") if isinstance(summary.get("legacy_agents"), dict) else {}
    regression = summary.get("regression") if isinstance(summary.get("regression"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}
    pull_request_queue = summary.get("pull_request_queue") if isinstance(summary.get("pull_request_queue"), dict) else {}
    repo_state_risk = summary.get("repo_state_risk") if isinstance(summary.get("repo_state_risk"), dict) else {}
    resource_risk = summary.get("agent_resource_risk") if isinstance(summary.get("agent_resource_risk"), dict) else {}
    next_actions = summary.get("next_agent_actions") if isinstance(summary.get("next_agent_actions"), dict) else {}
    agent_health = summary.get("agent_health") if isinstance(summary.get("agent_health"), dict) else {}
    health_agents = agent_health.get("agents") if isinstance(agent_health.get("agents"), dict) else {}

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
            gate_text = review_gate_detail(item.get("review_gate") if isinstance(item.get("review_gate"), dict) else {})
            pr_queue_lines.append(
                "- "
                f"merge-ready {item.get('owner_agent')} -> {item.get('repo')} #{item.get('number')} "
                f"checks={checks.get('success', 0)}/{checks.get('failed', 0)}/{checks.get('pending', 0)}"
                f"{detail_text}{gate_text} {item.get('url')}"
            )
    for item in pull_request_queue.get("top_items", [])[:8]:
        if isinstance(item, dict):
            checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
            check_detail = check_rollup_detail(checks)
            detail_text = f" {check_detail}" if check_detail else ""
            gate_text = review_gate_detail(item.get("review_gate") if isinstance(item.get("review_gate"), dict) else {})
            pr_queue_lines.append(
                "- "
                f"{item.get('owner_agent')} -> {item.get('repo')} #{item.get('number')} {item.get('merge_state')} "
                f"checks={checks.get('success', 0)}/{checks.get('failed', 0)}/{checks.get('pending', 0)}"
                f"{detail_text}{gate_text} action={item.get('action_category')}:{item.get('action')} {item.get('url')}"
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
    resource_lines = [
        (
            "- agent 资源风险："
            f"high={resource_risk.get('high_count', 'unknown')}；"
            f"medium={resource_risk.get('medium_count', 'unknown')}。"
        )
    ]
    for item in resource_risk.get("top_items", [])[:8]:
        if isinstance(item, dict):
            token_usage = item.get("token_usage")
            token_text = f"{int(token_usage):,}" if isinstance(token_usage, int) else "unknown"
            resource_lines.append(
                "- "
                f"{item.get('agent')} {item.get('severity')} tokens={token_text} "
                f"log_bytes={item.get('log_bytes')} action={item.get('action')}"
            )
    repo_risk_lines = [
        (
            "- 仓库状态风险："
            f"count={repo_state_risk.get('count', 0)}；"
            f"by_repo={repo_state_risk.get('by_repo', {})}；"
            f"by_owner={repo_state_risk.get('by_owner_agent', {})}；"
            f"by_category={repo_state_risk.get('by_category', {})}。"
        )
    ]
    for item in repo_state_risk.get("top_items", [])[:8]:
        if isinstance(item, dict):
            repo_risk_lines.append(
                "- "
                f"{item.get('owner_agent')} -> {item.get('repo')} priority={item.get('priority')} "
                f"category={item.get('category')} action={item.get('action')} "
                f"summary={item.get('summary')}"
            )
    next_action_lines = [
        (
            "- 下一步行动项："
            f"count={next_actions.get('count', 0)}；"
            f"by_agent={next_actions.get('by_agent', {})}；"
            f"by_category={next_actions.get('by_category', {})}。"
        )
    ]
    for item in next_actions.get("top_items", [])[:8]:
        if isinstance(item, dict):
            evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
            url = evidence.get("url")
            url_text = f" {url}" if url else ""
            next_action_lines.append(
                "- "
                f"{item.get('agent')} -> {item.get('repo')} priority={item.get('priority')} "
                f"category={item.get('category')} action={item.get('action')} "
                f"summary={item.get('summary')}{url_text}"
            )

    health_lines = [
        (
            "- Agent 健康评分："
            f"average={agent_health.get('average_score', 'unknown')}；"
            f"low={agent_health.get('low_score_agents', [])}；"
            f"model={agent_health.get('model', 'unknown')}。"
        )
    ]
    for agent_id, raw_item in sorted(health_agents.items()):
        item = raw_item if isinstance(raw_item, dict) else {}
        reason_text = "；".join(str(reason) for reason in (item.get("reasons") if isinstance(item.get("reasons"), list) else [])[:3])
        action_text = "；".join(str(action) for action in (item.get("actions") if isinstance(item.get("actions"), list) else [])[:2])
        health_lines.append(
            "- "
            f"{agent_id}: score={item.get('score')} label={item.get('label')} status={item.get('status')} "
            f"reason={reason_text or '无'} action={action_text or '继续推进'}"
        )

    return "\n".join(
        [
            "# gotouhou 审计 agent 三小时汇报",
            "",
            f"审计时间：{summary.get('generated_at', '')}",
            "",
            "## 结论",
            "",
            f"- 已将开发管理模型收敛为 {len(MANAGED_AGENT_IDS)} 个 agent：{', '.join(MANAGED_AGENT_IDS)}。",
            "- 已去除旧分片调度概念；manager 15 分钟采样 agent 状态、worktree、PR、资源和日志停滞信号，非运行即补启，并把 next_actions 写回提示词。",
            f"- 当前运行中：{', '.join(active) if active else '无'}；失败：{', '.join(failed) if failed else '无'}。",
            f"- 整体完成度仍按约 {PROJECT_COMPLETION_PERCENT}% 估算；主线仍是 Phase 3 服务器权威在线 MVP，同时补 Phase 2/6/8 客户端弹幕与 UI。",
            cleanup_line,
            "",
            "## 新 agent 状态",
            "",
            *agent_lines,
            "",
            "## Agent 健康评分",
            "",
            *health_lines,
            "",
            "## 本轮动作",
            "",
            *action_lines,
            "",
            "## Git 与版本风险",
            "",
            f"- 当前 dirty 仓库：{', '.join(dirty_repos) if dirty_repos else '无'}。",
            pr_line,
            *repo_risk_lines,
            *pr_queue_lines,
            "- 新 agent 使用独立 worktree/工作目录，避免直接覆盖旧 agent 未提交内容；审计 agent 继续判断旧 dirty work 是否应整理成 PR 或废弃。",
            "- 简单线性改动可阶段性提交；跨仓、协议/网络/安全、回归修复和并行开发必须 branch + PR。",
            "",
            "## 下一步行动",
            "",
            *next_action_lines,
            "",
            "## 回归与环境",
            "",
            f"- 最新 regression：ok={regression.get('ok', 'unknown')}，failed={regression.get('failed_count', 'unknown')}。",
            "- 服务端回归使用 `docker-compose`；Godot 纯渲染器/RenderingDevice 缺 GPU 失败可忽略，脚本/合同失败不能忽略。",
            "",
            "## Token 与停滞风险",
            "",
            *resource_lines,
            "- 当前没有新 agent 停滞证据；运行中的 agent 不应被三小时邮件打断。",
            "- 并行输出速度仍高于合并与整理速度；SpellKard 是唯一明显积压点。",
            "",
            "## 下个三小时方向",
            "",
            "- client-agent：优先把弹幕玩法、Boss/实例/世界 Boss 本地合同、Replay/练习和服务端协议字段对齐到可 headless 验证状态。",
            "- battle-server-agent：优先推进房间生命周期、Boss 战斗实例、输入窗口、Replay/hash、结算签名和 protocol audit。",
            "- nakama-server-agent：优先推进 PVP 匹配队列、资格验证、battle ticket/allocation、Nakama RPC/WSS 合同和 PostgreSQL audit。",
            "- audit-agent：继续用中文审计提交和方向，三小时邮件只保留结论、阻塞和下一步，不再粘贴长日志。",
            "- project-manager-agent：每轮读取 docs/dev、日志、PR、回归和 git 状态，主动推进 dirty/ahead/PR/停滞收敛、提示词和版本流程。",
        ]
    ) + "\n"


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    now = utcnow()
    agents_dir = root / ".agents"
    keyring = load_keyring(Path(args.key_file).resolve())
    previous = read_json(agents_dir / "goal-agent-summary.json", {})

    repos = {name: collect_repo(root, name) for name in DEFAULT_REPOS}
    repo_state_risk = build_repo_state_risk(repos)
    pull_requests = collect_pull_requests(root, now)
    pull_request_queue = build_pull_request_queue(pull_requests)
    runtime = collect_runtime(root)
    regression = read_json(root / ".agents" / "checks" / "latest-regression.json", {"missing": True})
    legacy_agents = collect_legacy_agents(root)
    agents: dict[str, Any] = {}
    actions: list[dict[str, Any]] = []
    should_persist = not args.dry_run and not args.no_start

    for agent_id, agent in AGENTS.items():
        key_assignment = select_key_alias(agent, keyring)
        worktree = prepare_worktree(root, agent_id, agent, args.dry_run or args.no_start)
        workdir = Path(str(worktree["path"]))
        paths = write_personas(root, agent_id, agent, workdir, key_assignment, previous) if should_persist else {
            "persona": str(root / ".agents" / "personas" / f"{agent_id}.md"),
            "prompt": str(root / ".agents" / "agent-prompts" / f"{agent_id}.md"),
            "workspace": str(root / ".agents" / "workspaces" / agent_id / "README.md"),
        }
        lock = lock_status(root, agent_id, now)
        log = log_info(current_log_path(root, agent_id, lock))
        start, reason = should_start_agent(lock, log, args.force_start, now)
        result: dict[str, Any] | None = None
        if start and not lock.get("alive") and worktree.get("ready", False):
            if args.no_start:
                result = {
                    "started": False,
                    "reason": "no-start",
                    "would_start": True,
                    "key_alias": key_assignment.get("alias"),
                }
            else:
                result = start_agent(
                    root,
                    agent_id,
                    workdir,
                    Path(paths["persona"]),
                    Path(paths["prompt"]),
                    key_assignment,
                    args.dry_run,
                )
            actions.append({"type": "start-goal-agent", "agent": agent_id, "reason": reason, "result": result})
            lock = lock_status(root, agent_id, utcnow())
            log = log_info(current_log_path(root, agent_id, lock))
        elif start and not worktree.get("ready", False):
            action_type = "would-prepare-worktree" if args.no_start else "worktree-blocked"
            actions.append({"type": action_type, "agent": agent_id, "reason": str(worktree.get("error") or worktree.get("output") or "worktree not ready")})

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
            "worktree_state": collect_git_worktree_state(workdir),
            "lock": lock,
            "runtime_log": log,
            "status": status,
            "progress": bool(lock.get("alive") or log.get("bytes", 0) or (result or {}).get("started")),
            "reason": reason,
        }
    agent_resource_risk = build_agent_resource_risk(agents, legacy_agents, now)
    next_agent_actions = build_next_agent_actions(pull_request_queue, agent_resource_risk, repo_state_risk, agents)
    agent_health = build_agent_health(agents, repo_state_risk, pull_request_queue, agent_resource_risk, next_agent_actions)

    summary = {
        "version": 2,
        "manager": "goal_agent_manager",
        "generated_at": iso(utcnow()),
        "report_interval_hours": REPORT_INTERVAL_HOURS,
        "project_completion_percent": PROJECT_COMPLETION_PERCENT,
        "root": str(root),
        "dry_run": bool(args.dry_run),
        "read_only_sample": bool(args.dry_run or args.no_start),
        "resampled_after_actions": True,
        "repos": repos,
        "repo_state_risk": repo_state_risk,
        "pull_requests": pull_requests,
        "pull_request_queue": pull_request_queue,
        "runtime": runtime,
        "regression": regression,
        "legacy_agents": legacy_agents,
        "agent_resource_risk": agent_resource_risk,
        "agent_health": agent_health,
        "next_agent_actions": next_agent_actions,
        "agents": agents,
        "actions": actions,
        "action_count": len(actions),
        "started_count": sum(1 for item in actions if (item.get("result") or {}).get("started")),
        "failures": [
            item
            for item in actions
            if item.get("result")
            and not item["result"].get("started")
            and item["result"].get("reason") not in {"dry-run", "read-only-sample", "no-start"}
        ],
        "previous_generated_at": previous.get("generated_at") if isinstance(previous, dict) else None,
    }
    audit_text = build_audit_report(summary)
    reports_dir = root / ".agents" / "reports"
    audit_path = reports_dir / "audit-agent-latest.md"
    plan_path = reports_dir / "plan-audit-latest.md"
    if should_persist:
        atomic_write_text(audit_path, audit_text)
        atomic_write_text(plan_path, audit_text)
        refresh_personas_from_summary(root, summary)
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
    if args.no_start:
        summary["non_authoritative_reason"] = "--no-start does not launch agents and must not overwrite watchdog state"
    if should_persist:
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
        "Model: identity-based goal agents; non-running agents are restarted; dirty/ahead/behind, PR, resource, and stale-log signals become next actions.",
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


def compact_summary(summary: dict[str, Any]) -> dict[str, Any]:
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    return {
        "version": summary.get("version"),
        "manager": summary.get("manager"),
        "generated_at": summary.get("generated_at"),
        "root": summary.get("root"),
        "dry_run": summary.get("dry_run"),
        "read_only_sample": summary.get("read_only_sample"),
        "non_authoritative_reason": summary.get("non_authoritative_reason"),
        "action_count": summary.get("action_count"),
        "started_count": summary.get("started_count"),
        "agents": {
            agent_id: {
                "repo": agent.get("repo"),
                "status": agent.get("status"),
                "key_alias": agent.get("key_alias"),
                "workdir": agent.get("workdir"),
                "log": {
                    "path": runtime_log.get("path"),
                    "bytes": runtime_log.get("bytes"),
                    "sampled_bytes": runtime_log.get("sampled_bytes"),
                    "tail_truncated": runtime_log.get("tail_truncated"),
                    "token_usage": runtime_log.get("token_usage"),
                    "exit_status": runtime_log.get("exit_status"),
                },
            }
            for agent_id, raw_agent in sorted(agents.items())
            if isinstance(raw_agent, dict)
            for agent in (raw_agent,)
            for runtime_log in (agent.get("runtime_log") if isinstance(agent.get("runtime_log"), dict) else {},)
        },
        "repo_state_risk": summary.get("repo_state_risk"),
        "agent_health": summary.get("agent_health"),
        "pull_request_queue": {
            key: value
            for key, value in (summary.get("pull_request_queue") if isinstance(summary.get("pull_request_queue"), dict) else {}).items()
            if key not in {"items"}
        },
        "agent_resource_risk": summary.get("agent_resource_risk"),
        "next_agent_actions": summary.get("next_agent_actions"),
        "regression": {
            key: regression.get(key)
            for key in ("ok", "failed_count", "ignored_count", "generated_at")
            for regression in (summary.get("regression") if isinstance(summary.get("regression"), dict) else {},)
        },
        "reports": {
            key: {
                "path": report.get("path"),
                "updated_at": report.get("updated_at"),
            }
            for key, raw_report in (summary.get("reports") if isinstance(summary.get("reports"), dict) else {}).items()
            if isinstance(raw_report, dict)
            for report in (raw_report,)
        },
        "failures": summary.get("failures"),
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/root/gotouhou")
    parser.add_argument("--key-file", default=DEFAULT_KEY_FILE)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-start", action="store_true", help="sample only; do not launch agents or persist authoritative watchdog state")
    parser.add_argument("--force-start", action="store_true", help="start agents even if they completed recently")
    parser.add_argument("--full-output", action="store_true", help="print the complete JSON summary instead of the compact operational view")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    summary = build_summary(args)
    output = summary if args.full_output else compact_summary(summary)
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
