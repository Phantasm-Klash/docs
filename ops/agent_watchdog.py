#!/usr/bin/env python3
"""Watch gotouhou manager/agent progress and start fallback agents when needed.

The watchdog is host-local operational glue. It records state under
`/root/gotouhou/.agents`, keeps the hourly progress email short and actionable,
and uses `codex exec` as a fallback when the in-app manager is not making
progress.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


DEFAULT_REPOS = ("docs", "SpellKard", "Gensoulkyo", "PhK-BattleServer", "PhK-Protocol")
DEFAULT_KEY_FILE = "/root/.codex/keys"
DEFAULT_GODOT_LINUX = "/root/gotouhou/Godot_v4.7-stable_linux.x86_64"
DEFAULT_GITHUB_PROXY = "socks5h://10.10.10.108:10808"
DEFAULT_GH_PROXY = "socks5://10.10.10.108:10808"
GOAL_MODE = "codex-/goal-active"
GITHUB_ORG = "Phantasm-Klash"
UTC = dt.timezone.utc

KEY_ALIAS_PREFERENCES: dict[str, tuple[str, ...]] = {
    "spellkard-bullet": ("spellkard-bullet", "spellkard", "other"),
    "spellkard-ui": ("spellkard-ui", "spellkard", "other"),
    "gensoulkyo-lobby": ("gensoulkyo-lobby", "gensoulkyo", "other"),
    "phk-battle-server": ("phk-battle-server", "phk", "battle-server", "battle", "other"),
    "change-describer": ("change-describer", "docs", "ops", "other"),
    "plan-auditor": ("plan-auditor", "docs", "ops", "other"),
    "bugfix-spellkard-godot-headless": ("spellkard-ui", "spellkard-bullet", "spellkard", "other"),
    "manager": ("manager", "ops", "other"),
}

DEVELOPMENT_SCOPE_DIRECTIVES: dict[str, str] = {
    "gensoulkyo-lobby": """你是 gotouhou 的 Gensoulkyo/Nakama 业务服 worker。工作区 `/root/gotouhou/Gensoulkyo`。当前主线是 Phase 3：Nakama + Go Runtime 负责账号、业务 RPC/WSS、大厅、匹配、battle allocation/ticket、结算验签和持久化；C++ BattleServer 负责高频战斗。请先阅读 `/root/gotouhou/docs/dev/progress.md`、`docs/dev/gotouhou/00_overview/network_security_and_server_split_plan.md`、`04_server_database_economy/server_stack.md`、`04_server_database_economy/client_server_connection.md`。本轮优先做：验证或补齐 Nakama SDK tag-build/注册 RPC 源码测试，推进 PostgreSQL audit sink 与 battle ticket/allocation/replay audit repository wiring，保持 HTTP fallback 只作为契约测试。禁止把高频 tick、Boss 伤害、奖励发放或客户端提交结果做成 Go HTTP 生产权威路径。测试优先使用 Docker 容器化回归；如果仓库没有 Dockerfile/compose 或 `docker-compose` 不可用，运行 Go 单元测试和 HTTP/Nakama handler 测试并把 Docker 缺口写入最终状态。""",
    "phk-battle-server": """你是 gotouhou 的 PhK-BattleServer C++ worker。工作区 `/root/gotouhou/PhK-BattleServer`。当前任务必须服务 Phase 3：C++ BattleServer 是高频战斗权威模拟与结果签名边界，不能写库存、奖励、钱包或数据库。请先阅读 `/root/gotouhou/docs/dev/progress.md`、`docs/dev/gotouhou/02_networked_match/deterministic_lockstep_review.md`、`00_overview/network_security_and_server_split_plan.md`、`08_game_modes/mode_shared_server_interfaces.md`。本轮优先做真实生产依赖替换前的可测试边界：对接 PhK-Protocol 生成的 C++ protobuf 形状或更严格 manifest gate，补 Ed25519/X25519/KCP/AEAD 接口适配层测试，扩展最小 1v1 60Hz authoritative tick 的 replay/hash fixture。保持现有 scaffold 明确标注为开发占位。测试优先使用 Docker 构建/回归；如果没有 Dockerfile/compose，运行 `tools/check_battle_server.py --build` 或等价 CMake/CTest 并记录 Docker 缺口。""",
    "spellkard-ui": """你是 gotouhou 的 SpellKard Godot UI worker。工作区 `/root/gotouhou/SpellKard`。当前任务服务 Phase 6：把现有 `ClientMenuPageModel.page_spec()`、`UIScreenModel.page_layout()`、row section/ui_control metadata 落到更接近正式 Godot Control 场景的运行时界面。请先阅读 `/root/gotouhou/docs/dev/progress.md`、`docs/dev/gotouhou/05_content_assets_ui/ui_screens.md`、`00_overview/i18n_and_theme_policy.md`。本轮优先做 Play/Collection/Community/Player Settings 二级页的焦点、手柄/键鼠可操作、文本不溢出、素材 provenance 和 headless 验证。Godot Linux 可执行文件位于 `/root/gotouhou/Godot_v4.7-stable_linux.x86_64`；优先从 `/root/gotouhou/SpellKard/godot` 运行 `--headless --path . --script ../tools/client_ui_smoke_test.gd`、`asset_manifest_check.gd` 和必要的静态检查。服务器无显卡导致的纯渲染器/RenderingDevice 失败可以标记为环境 blocked，不算功能失败；但 GDScript parse/compile/type error、脚本加载失败、UI health 失败必须修复。首页仍只保留 Play、Collection、Community、Player Settings 四入口；不要把 debug dashboard 重新暴露到首页；不要引入未授权东方/商业素材。""",
    "spellkard-bullet": """你是 gotouhou 的 SpellKard 弹幕/Replay worker。工作区 `/root/gotouhou/SpellKard`。当前任务服务 Phase 2 与 Phase 8 的客户端展示侧：Boss spellbook、Pattern Lab 和 deterministic preview 只能作为本地练习、预览、性能预算和 Replay 展示合同，线上 Boss HP、伤害、奖励、结算仍由服务端权威。请先阅读 `/root/gotouhou/docs/dev/progress.md`、`docs/dev/gotouhou/01_core_stg_client/bullet_pattern_system.md`、`01_core_stg_client/performance_and_bullet_limits.md`、`08_game_modes/world_boss_mode.md`、`08_game_modes/instance_boss_mode.md`。本轮优先补 spellbook preview 的 golden fixture、Replay metadata 校验、弹量预算回归和 Godot headless 检查。Godot Linux 可执行文件位于 `/root/gotouhou/Godot_v4.7-stable_linux.x86_64`；优先从 `/root/gotouhou/SpellKard/godot` 运行 `--headless --path . --script ../tools/boss_pattern_catalog_check.gd`、必要时运行 `client_smoke_test.gd` 和静态检查。服务器无显卡导致的纯渲染器/RenderingDevice 失败可以标记为环境 blocked，不算功能失败；但 GDScript parse/compile/type error、脚本加载失败、弹幕合同失败必须修复。不要继续无测试扩张 catalog 数量；不要复制商业符卡名、关卡脚本、音乐、美术或专有设定。""",
}

GIT_FLOW_PROMPT = """版本控制和 PR 流程：
- 不直接在 `main` 开发。先 `git fetch --prune origin`，从最新 `origin/main` 创建 scope 分支，例如 `agent/<scope>/<YYYYMMDD-HHMM>`。
- 阶段性提交：每个可验证阶段都要 commit，提交信息写清功能范围、验证方式和剩余风险。
- 推送分支并创建 PR；PR 正文必须包含变更摘要、测试结果、阻塞风险、是否涉及协议/网络/安全、是否需要 docs/dev 方向调整。
- 除非 manager 明确授权合并，否则不要直接推 `main`。如果仓库规则允许绕过，也优先保留 PR 和分支历史。
- 提交或推送前使用 `/root/gotouhou/.agents/locks/git-<repo>.lock`，避免同仓并发冲突。
- watchdog 查出的代码回归必须开独立 `fix/<area>` 分支和 PR，测试通过后请求合并；若分支保护阻止合并，写入状态和邮件，不得假报已合并。
- PR 审批前必须读 PR diff、相关 docs/dev 路线和测试结果；审批不等于自动合并。
"""


DEFAULT_SCOPES: dict[str, dict[str, Any]] = {
    "spellkard-bullet": {
        "nickname": "Mendel",
        "agent_id": "019f0e84-8d8d-7510-be5e-abd7c4dd2b16",
        "repo": "SpellKard",
        "paths": (
            "dev/progress.md",
            "godot/scripts/boss_pattern_catalog.gd",
            "godot/scripts/boss_spellbook_model.gd",
            "godot/scripts/pattern_lab_model.gd",
            "godot/scripts/replay_list_model.gd",
            "godot/scripts/replay_store.gd",
            "tests/README.md",
            "tools/README.md",
            "tools/boss_pattern_catalog_check.gd",
            "tools/ci_static_checks.py",
        ),
        "summary": "Bullet spellbook and Pattern Lab integration",
    },
    "spellkard-ui": {
        "nickname": "Copernicus",
        "agent_id": "019f0e84-d497-7473-994d-d1842963266a",
        "repo": "SpellKard",
        "paths": (
            "dev/progress.md",
            "godot/assets/asset_manifest.json",
            "godot/assets/licenses/README.md",
            "godot/scenes/ui",
            "godot/scripts/client_menu_page_model.gd",
            "godot/scripts/main.gd",
            "godot/scripts/ui_screen_model.gd",
            "godot/themes",
            "tools/asset_manifest_check.gd",
            "tools/ci_static_checks.py",
            "tools/client_ui_smoke_test.gd",
        ),
        "summary": "Frontend layout metadata, assets, and UI checks",
    },
    "gensoulkyo-lobby": {
        "nickname": "Pascal",
        "agent_id": "019f0e85-dc60-7151-b15c-3cd8715530f3",
        "repo": "Gensoulkyo",
        "paths": (
            "cmd/gensoulkyo_nakama",
            "dev/progress.md",
            "runtime/core",
            "runtime/nakamaapi",
        ),
        "summary": "Nakama lobby lifecycle and security",
    },
    "phk-battle-server": {
        "nickname": "Franklin",
        "agent_id": "019f0e86-2176-7da2-98bb-495334d778f2",
        "repo": "PhK-BattleServer",
        "paths": (
            "dev/progress.md",
            "docs/architecture.md",
            "include/phk/battle",
            "src",
            "tests/battle_server_tests.cpp",
            "tools/check_battle_server.py",
        ),
        "summary": "C++ battle server reconnect and result boundaries",
    },
    "change-describer": {
        "nickname": "Narrator",
        "agent_id": "",
        "repo": "docs",
        "paths": (
            "dev/progress.md",
            "ops/agent_watchdog.py",
            "ops/hourly_progress_mail.py",
        ),
        "summary": "中文功能变更摘要，替换邮件中的低可读性日志",
        "continuous": True,
        "kind": "summary",
    },
    "plan-auditor": {
        "nickname": "Auditor",
        "agent_id": "",
        "repo": "docs",
        "paths": (
            "dev/gotouhou",
            "dev/progress.md",
            "docs/development-progress.md",
        ),
        "summary": "审计实现方向是否符合 docs/dev 开发计划，并给出 agent 提示词调整建议",
        "continuous": True,
        "kind": "audit",
    },
}


def utcnow() -> dt.datetime:
    return dt.datetime.now(UTC)


def hour_bucket(ts: dt.datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y%m%dT%H")


def iso(ts: dt.datetime) -> str:
    return ts.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def snapshot_bucket(snapshot: dict[str, Any]) -> str | None:
    raw_bucket = snapshot.get("hour_bucket")
    if isinstance(raw_bucket, str) and raw_bucket:
        return raw_bucket
    generated = parse_iso(snapshot.get("generated_at") if isinstance(snapshot.get("generated_at"), str) else None)
    if generated is not None:
        return hour_bucket(generated)
    return None


def command_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HOME", "/root")
    env.setdefault("XDG_CONFIG_HOME", "/root/.config")
    env.setdefault("GOCACHE", "/root/.cache/go-build")
    env.setdefault("GOPATH", "/root/go")
    if extra:
        env.update(extra)
    return env


def github_env() -> dict[str, str]:
    env = command_env()
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        env.setdefault(name, DEFAULT_GITHUB_PROXY)
    return env


def gh_env() -> dict[str, str]:
    env = command_env()
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
        env.setdefault(name, DEFAULT_GH_PROXY)
    return env


def run_command(command: list[str], cwd: Path, timeout: int = 20, env: dict[str, str] | None = None) -> tuple[int, str]:
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
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return completed.returncode, completed.stdout.strip()


def run_json_command(command: list[str], cwd: Path, timeout: int = 30, env: dict[str, str] | None = None) -> Any:
    code, output = run_command(command, cwd, timeout=timeout, env=env)
    if code != 0 or not output:
        return None
    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return None


def run_git(repo: Path, args: list[str], timeout: int = 20) -> str:
    if not (repo / ".git").exists():
        return "not a git repository"
    _, output = run_command(["git", *args], repo, timeout=timeout)
    return output or ""


def read_json(path: Path, default: Any) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
        handle.write("\n")


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_key_alias(line: str, index: int) -> tuple[str, str] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if ":" in stripped and not stripped.startswith("sk-"):
        alias, value = stripped.split(":", 1)
        alias = alias.strip()
        value = value.strip()
    elif "=" in stripped:
        alias, value = stripped.split("=", 1)
        alias = alias.strip()
        value = value.strip()
    else:
        alias = f"key{index}"
        value = stripped
    if not alias or not value:
        return None
    return alias, value


def load_keyring(key_file: Path) -> dict[str, Any]:
    aliases: dict[str, str] = {}
    try:
        mode = key_file.stat().st_mode & 0o777
        lines = key_file.read_text(encoding="utf-8", errors="replace").splitlines()
    except FileNotFoundError:
        return {"path": str(key_file), "exists": False, "aliases": {}, "permissions": None, "permission_warning": False}
    except OSError as exc:
        return {
            "path": str(key_file),
            "exists": True,
            "aliases": {},
            "permissions": None,
            "permission_warning": True,
            "error": str(exc),
        }

    index = 1
    for line in lines:
        parsed = parse_key_alias(line, index)
        if parsed is None:
            continue
        alias, value = parsed
        aliases[alias] = value
        index += 1

    return {
        "path": str(key_file),
        "exists": True,
        "aliases": aliases,
        "permissions": oct(mode),
        "permission_warning": bool(mode & 0o077),
    }


def keyring_public_summary(keyring: dict[str, Any]) -> dict[str, Any]:
    aliases = keyring.get("aliases") if isinstance(keyring.get("aliases"), dict) else {}
    return {
        "path": keyring.get("path", DEFAULT_KEY_FILE),
        "exists": bool(keyring.get("exists")),
        "aliases": sorted(str(alias) for alias in aliases),
        "alias_count": len(aliases),
        "permissions": keyring.get("permissions"),
        "permission_warning": bool(keyring.get("permission_warning")),
        "error": keyring.get("error"),
    }


def select_key_alias(scope_id: str, keyring: dict[str, Any]) -> dict[str, Any]:
    aliases = keyring.get("aliases") if isinstance(keyring.get("aliases"), dict) else {}
    preferences = KEY_ALIAS_PREFERENCES.get(scope_id, (scope_id, "other"))
    for alias in preferences:
        if alias in aliases:
            return {
                "scope": scope_id,
                "alias": alias,
                "source": "preferred",
                "available": True,
                "preferences": list(preferences),
            }
    return {
        "scope": scope_id,
        "alias": None,
        "source": "missing",
        "available": False,
        "preferences": list(preferences),
    }


def selected_key_value(selection: dict[str, Any], keyring: dict[str, Any]) -> str | None:
    alias = selection.get("alias")
    aliases = keyring.get("aliases") if isinstance(keyring.get("aliases"), dict) else {}
    if isinstance(alias, str):
        value = aliases.get(alias)
        return str(value) if value else None
    return None


def pid_alive(pid: int | None) -> bool:
    if not pid or pid <= 1:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def systemd_unit_active(unit: str | None) -> bool:
    if not unit:
        return False
    code, output = run_command(["systemctl", "is-active", unit], Path("/"), timeout=10)
    return code == 0 and output.strip() == "active"


def newest_file_mtime(paths: list[Path]) -> float | None:
    mtimes: list[float] = []
    for path in paths:
        if path.exists():
            mtimes.append(path.stat().st_mtime)
    return max(mtimes) if mtimes else None


def collect_repo(root: Path, repo_name: str, now: dt.datetime) -> dict[str, Any]:
    repo = root / repo_name
    branch = run_git(repo, ["branch", "--show-current"]) or "(detached or unknown)"
    status = run_git(repo, ["status", "--short", "--branch"])
    head = run_git(repo, ["rev-parse", "--short", "HEAD"]) or "(no head)"
    commits = run_git(repo, ["log", "--since=1 hour ago", "--oneline", "--decorate", "--max-count=20"])
    dirty_lines = [line for line in status.splitlines() if line and not line.startswith("## ")]
    return {
        "repo": repo_name,
        "path": str(repo),
        "branch": branch,
        "head": head,
        "status": status,
        "dirty_count": len(dirty_lines),
        "dirty_paths": dirty_lines[:20],
        "commits_last_hour": commits.splitlines() if commits else [],
        "collected_at": iso(now),
    }


def collect_pull_requests(root: Path, now: dt.datetime) -> dict[str, Any]:
    repos: dict[str, Any] = {}
    for repo_name in DEFAULT_REPOS:
        repo_root = root / repo_name
        command = [
            "gh",
            "pr",
            "list",
            "--repo",
            f"{GITHUB_ORG}/{repo_name}",
            "--state",
            "open",
            "--json",
            "number,title,headRefName,baseRefName,author,isDraft,mergeStateStatus,url,updatedAt",
        ]
        cwd = repo_root if repo_root.exists() else root
        code, output = run_command(command, cwd, timeout=30, env=gh_env())
        fallback_output = ""
        if code != 0:
            fallback_code, fallback_output = run_command(command, cwd, timeout=30)
            if fallback_code == 0:
                code, output = fallback_code, fallback_output
        payload = None
        if code == 0 and output:
            try:
                payload = json.loads(output)
            except json.JSONDecodeError:
                payload = None
        if isinstance(payload, list):
            repos[repo_name] = {
                "repo": repo_name,
                "open_count": len(payload),
                "items": payload[:20],
                "collected_at": iso(now),
                "status": code,
            }
        else:
            repos[repo_name] = {
                "repo": repo_name,
                "open_count": None,
                "items": [],
                "error": "gh pr list failed or returned invalid JSON",
                "status": code,
                "output_tail": (output + ("\nfallback:\n" + fallback_output if fallback_output else ""))[-1000:],
                "collected_at": iso(now),
            }
    return repos


def scoped_status(root: Path, scope: dict[str, Any]) -> tuple[str, str]:
    repo = root / str(scope["repo"])
    paths = [str(path) for path in scope.get("paths", ())]
    status = run_git(repo, ["status", "--short", "--", *paths])
    diffstat = run_git(repo, ["diff", "--stat", "--", *paths])
    text = "\n".join([status, diffstat]).strip()
    return text, sha256_text(text)


def repo_has_foreign_active_work(root: Path, repo_name: str, scope_id: str, repos: dict[str, Any]) -> tuple[bool, str]:
    repo = repos.get(repo_name) if isinstance(repos.get(repo_name), dict) else {}
    branch = str(repo.get("branch", ""))
    dirty_count = int(repo.get("dirty_count", 0) or 0)
    if dirty_count <= 0:
        return False, ""
    if repo_name == "docs" and scope_id in {"change-describer", "plan-auditor"}:
        return False, ""
    if branch.startswith(f"agent/{scope_id}/"):
        return False, ""
    if branch.startswith("fix/"):
        return True, f"{repo_name} is on dirty bugfix branch {branch}; defer normal scope {scope_id}"
    if branch.startswith("agent/") and not branch.startswith(f"agent/{scope_id}/"):
        return True, f"{repo_name} is on dirty branch {branch} owned by another scope; defer {scope_id}"
    return True, f"{repo_name} has uncommitted work on {branch}; defer {scope_id}"


def collect_manager(root: Path, now: dt.datetime, stale_minutes: int) -> dict[str, Any]:
    agents_dir = root / ".agents"
    status_path = agents_dir / "manager-status.md"
    heartbeat_path = agents_dir / "manager-heartbeat.json"
    heartbeat = read_json(heartbeat_path, {})

    status_mtime = newest_file_mtime([status_path, heartbeat_path])
    age_seconds = None
    if status_mtime is not None:
        age_seconds = max(0, int(now.timestamp() - status_mtime))

    stored_mode = "unknown"
    if status_path.exists():
        text = status_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("Mode:"):
                stored_mode = line.split(":", 1)[1].strip()
                break

    return {
        "mode": GOAL_MODE,
        "stored_mode": stored_mode,
        "status_path": str(status_path),
        "heartbeat_path": str(heartbeat_path),
        "heartbeat": heartbeat if isinstance(heartbeat, dict) else {},
        "age_seconds": age_seconds,
        "stale": age_seconds is None or age_seconds > stale_minutes * 60,
        "stale_after_minutes": stale_minutes,
        "updated_at": iso(dt.datetime.fromtimestamp(status_mtime, UTC)) if status_mtime else None,
    }


def collect_systemd_mail(now: dt.datetime) -> dict[str, Any]:
    active_code, active_output = run_command(["systemctl", "is-active", "gotouhou-hourly-progress.timer"], Path("/"))
    enabled_code, enabled_output = run_command(["systemctl", "is-enabled", "gotouhou-hourly-progress.timer"], Path("/"))
    status_code, status_output = run_command(
        ["systemctl", "status", "gotouhou-hourly-progress.service", "--no-pager", "-l"],
        Path("/"),
        timeout=20,
    )
    timers_code, timers_output = run_command(
        ["systemctl", "list-timers", "--all", "gotouhou*", "--no-pager"],
        Path("/"),
        timeout=20,
    )
    service_lines = [
        line.strip()
        for line in status_output.splitlines()
        if "Active:" in line or "Process:" in line or "Finished" in line or "Starting" in line
    ][:12]
    timer_lines = [line.strip() for line in timers_output.splitlines() if line.strip()][:6]
    return {
        "collected_at": iso(now),
        "timer_active": active_output,
        "timer_active_ok": active_code == 0,
        "timer_enabled": enabled_output,
        "timer_enabled_ok": enabled_code == 0,
        "service_status_code": status_code,
        "service_lines": service_lines,
        "timer_lines": timer_lines,
        "timer_command_status": timers_code,
    }


def find_docker_files(root: Path, repo_name: str) -> list[str]:
    repo = root / repo_name
    if not repo.exists():
        return []
    matches: list[str] = []
    for pattern in ("Dockerfile", "Dockerfile.*", "*.Dockerfile", "docker-compose*.yml", "docker-compose*.yaml", "compose*.yml", "compose*.yaml"):
        for path in repo.glob(pattern):
            if path.is_file():
                matches.append(str(path.relative_to(repo)))
    return sorted(set(matches))


def collect_runtime_environment(root: Path, now: dt.datetime, godot_bin: Path) -> dict[str, Any]:
    godot_exists = godot_bin.exists()
    godot_executable = os.access(godot_bin, os.X_OK) if godot_exists else False
    godot_code, godot_output = (127, "missing")
    if godot_exists and godot_executable:
        godot_code, godot_output = run_command([str(godot_bin), "--version"], root, timeout=20)
    docker_code, docker_output = run_command(["docker", "--version"], root, timeout=20)
    compose_code, compose_output = run_command(["docker-compose", "--version"], root, timeout=20)
    docker_files = {name: find_docker_files(root, name) for name in DEFAULT_REPOS}
    return {
        "collected_at": iso(now),
        "godot_linux": {
            "path": str(godot_bin),
            "exists": godot_exists,
            "executable": godot_executable,
            "version_status": godot_code,
            "version": godot_output.splitlines()[0] if godot_output else "",
        },
        "docker": {
            "available": docker_code == 0,
            "version": docker_output.splitlines()[0] if docker_output else "",
            "docker_compose_available": compose_code == 0,
            "docker_compose_version": compose_output.splitlines()[0] if compose_output else "",
            "repo_files": docker_files,
        },
    }


def pr_approval_checks(root: Path, repo_name: str, pr: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    if pr.get("isDraft"):
        blockers.append("draft PR")
    if pr.get("baseRefName") != "main":
        blockers.append(f"base is {pr.get('baseRefName')}, not main")
    if pr.get("mergeStateStatus") not in {"CLEAN", "HAS_HOOKS", "UNKNOWN"}:
        blockers.append(f"merge state {pr.get('mergeStateStatus')}")
    repo_root = root / repo_name
    if repo_name in {"Gensoulkyo", "PhK-BattleServer", "PhK-Protocol", "SpellKard"}:
        code, output = run_command(["python3", str(root / "docs" / "ops" / "protocol_audit_check.py")], root, timeout=120)
        if code != 0:
            blockers.append(f"protocol audit failed: {output[-500:]}")
    if repo_name == "SpellKard":
        godot = Path(DEFAULT_GODOT_LINUX)
        if not godot.exists() or not os.access(godot, os.X_OK):
            blockers.append("Godot Linux headless binary missing or not executable")
    if repo_name in {"Gensoulkyo", "PhK-BattleServer"} and not find_docker_files(root, repo_name):
        blockers.append("no Dockerfile/docker-compose files for server regression")
    if not repo_root.exists():
        blockers.append("local repository missing")
    return blockers


def maybe_approve_pull_requests(root: Path, pull_requests: dict[str, Any], approve: bool) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if not approve:
        return actions
    for repo_name, raw_repo in sorted(pull_requests.items()):
        repo_info = raw_repo if isinstance(raw_repo, dict) else {}
        for raw_pr in repo_info.get("items", []):
            pr = raw_pr if isinstance(raw_pr, dict) else {}
            number = pr.get("number")
            if not isinstance(number, int):
                continue
            blockers = pr_approval_checks(root, repo_name, pr)
            if blockers:
                actions.append(
                    {
                        "type": "pr-approval-skipped",
                        "repo": repo_name,
                        "number": number,
                        "url": pr.get("url"),
                        "blockers": blockers,
                    }
                )
                continue
            body = (
                "watchdog route/code review passed: docs/dev direction checked, "
                "local regression gates completed, no blocking PR metadata found."
            )
            code, output = run_command(
                ["gh", "pr", "review", str(number), "--repo", f"{GITHUB_ORG}/{repo_name}", "--approve", "--body", body],
                root / repo_name,
                timeout=60,
            )
            actions.append(
                {
                    "type": "pr-approved" if code == 0 else "pr-approval-failed",
                    "repo": repo_name,
                    "number": number,
                    "url": pr.get("url"),
                    "status": code,
                    "output": output[-1000:],
                }
            )
    return actions


def write_manager_files(root: Path, summary: dict[str, Any], now: dt.datetime) -> None:
    agents_dir = root / ".agents"
    heartbeat_path = agents_dir / "manager-heartbeat.json"
    status_path = agents_dir / "manager-status.md"
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    repos = summary.get("repos") if isinstance(summary.get("repos"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    key_assignments = summary.get("key_assignments") if isinstance(summary.get("key_assignments"), dict) else {}
    runtime = summary.get("runtime") if isinstance(summary.get("runtime"), dict) else {}
    godot = runtime.get("godot_linux") if isinstance(runtime.get("godot_linux"), dict) else {}
    docker = runtime.get("docker") if isinstance(runtime.get("docker"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}

    heartbeat = {
        "updated_at": iso(now),
        "mode": GOAL_MODE,
        "source": "agent_watchdog",
        "summary_path": summary.get("summary_path"),
        "action_count": summary.get("action_count", 0),
        "started_count": summary.get("started_count", 0),
        "scope_count": len(scopes),
    }
    write_json(heartbeat_path, heartbeat)

    lines = [
        "# gotouhou agent manager status",
        "",
        f"Updated: {iso(now)}",
        f"Mode: {GOAL_MODE}",
        "Goal: sustained multi-repository development for bullet engine, frontend/assets, Nakama lobby, and C++ battle server.",
        "Codex goal mode: fallback manager and worker prompts explicitly enter `/goal` sustained-target mode.",
        "Manager workspace: /root/gotouhou",
        "Git topology: root .git is invalid/empty; child repositories are the commit roots.",
        "Encoding policy: UTF-8, Linux LF.",
        "Key policy: agents receive per-scope keys from /root/.codex/keys; status files record aliases only.",
        "Version policy: development work uses feature branches, staged commits, pull requests, and protected-main reviews by default.",
        f"Godot Linux: {godot.get('path', DEFAULT_GODOT_LINUX)} exists={godot.get('exists')} executable={godot.get('executable')} version={godot.get('version', '')}",
        f"Docker: available={docker.get('available')} docker-compose={docker.get('docker_compose_available')} version={docker.get('docker_compose_version', '')}",
        "",
        "## Active goal scopes",
        "",
        "| Scope | Repo | Status | Key alias | Progress | Stalled | Head | Actions |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scope_id, raw_scope in sorted(scopes.items()):
        scope = raw_scope if isinstance(raw_scope, dict) else {}
        key_assignment = key_assignments.get(scope_id) if isinstance(key_assignments.get(scope_id), dict) else {}
        lines.append(
            "| "
            f"{scope_id} | {scope.get('repo', '')} | {scope.get('status', '')} | "
            f"{key_assignment.get('alias') or '(missing)'} | "
            f"{scope.get('progress', '')} | {scope.get('stalled_count', '')} | "
            f"{scope.get('head', '')} | {len(scope.get('actions', [])) if isinstance(scope.get('actions'), list) else 0} |"
        )

    lines.extend(
        [
            "",
            "## Repository sample",
            "",
            "| Repository | Head | Dirty | Recent commits |",
            "| --- | --- | --- | --- |",
        ]
    )
    for repo_name, raw_repo in sorted(repos.items()):
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        commits = repo.get("commits_last_hour") if isinstance(repo.get("commits_last_hour"), list) else []
        lines.append(
            "| "
            f"{repo_name} | {repo.get('head', '')} | {repo.get('dirty_count', '')} | "
            f"{len(commits)} in last hour |"
        )

    lines.extend(
        [
            "",
            "## Pull requests",
            "",
            "| Repository | Open PRs |",
            "| --- | --- |",
        ]
    )
    for repo_name, raw_prs in sorted(pull_requests.items()):
        prs = raw_prs if isinstance(raw_prs, dict) else {}
        lines.append(f"| {repo_name} | {prs.get('open_count', 'unknown')} |")

    lines.extend(["", "## Watchdog actions", ""])
    if actions:
        for action in actions:
            if not isinstance(action, dict):
                continue
            result = action.get("result") if isinstance(action.get("result"), dict) else {}
            lines.append(
                "- "
                f"{action.get('type', 'action')}: {action.get('reason', '')}; "
                f"started={result.get('started', False)}; result={result.get('reason', result.get('pid', ''))}"
            )
    else:
        lines.append("- None.")

    lines.extend(
        [
            "",
            "## Continuous policies",
            "",
            "- Hourly progress mail runs `agent_watchdog.py` before `hourly_progress_mail.py --brief`.",
            "- Missing scopes or stale manager heartbeat start a fallback `codex exec` worker.",
            "- Fallback prompts are written as Codex `/goal` sustained-target instructions.",
            "- Per-agent keys are injected through child process environment only; raw key values are never written to JSON, logs, mail, or git.",
            "- Scope stagnation uses the conservative two-sample rule.",
            "- Watchdog samples open PRs. With explicit `--approve-prs`, it reads code and docs/dev direction, runs gates, and approves only non-draft main-target PRs without blockers.",
            "- Network/protocol changes remain gated by `/root/gotouhou/docs/ops/protocol_audit_check.py`.",
        ]
    )
    status_path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def default_roster(now: dt.datetime) -> dict[str, Any]:
    scopes = {}
    for scope_id, scope in DEFAULT_SCOPES.items():
        scopes[scope_id] = {
            "scope": scope_id,
            "repo": scope["repo"],
            "nickname": scope["nickname"],
            "agent_id": scope["agent_id"],
            "status": "running",
            "source": "default-active-round-2",
            "last_seen_at": iso(now),
        }
    return {"version": 1, "created_at": iso(now), "scopes": scopes, "manager": {"status": GOAL_MODE}}


def merge_roster(roster: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    if not isinstance(roster, dict) or "scopes" not in roster:
        roster = default_roster(now)
    roster.setdefault("version", 1)
    roster.setdefault("created_at", iso(now))
    roster.setdefault("scopes", {})
    for scope_id, scope in DEFAULT_SCOPES.items():
        entry = roster["scopes"].setdefault(scope_id, {})
        entry.setdefault("scope", scope_id)
        entry.setdefault("repo", scope["repo"])
        entry.setdefault("nickname", scope["nickname"])
        entry.setdefault("agent_id", scope["agent_id"])
        entry.setdefault("status", "running")
        entry.setdefault("source", "default-active-round-2")
    roster["last_watchdog_at"] = iso(now)
    return roster


def load_previous_snapshot(snapshot_dir: Path) -> dict[str, Any] | None:
    snapshots = sorted(snapshot_dir.glob("*.json"))
    for path in reversed(snapshots):
        payload = read_json(path, None)
        if isinstance(payload, dict):
            return payload
    return None


def load_previous_distinct_snapshot(snapshot_dir: Path, current_bucket: str) -> dict[str, Any] | None:
    snapshots = sorted(snapshot_dir.glob("*.json"))
    for path in reversed(snapshots):
        payload = read_json(path, None)
        if not isinstance(payload, dict):
            continue
        if snapshot_bucket(payload) != current_bucket:
            return payload
    return None


def recent_log_mtime(root: Path, scope_id: str) -> float | None:
    logs_dir = root / ".agents" / "logs"
    if not logs_dir.exists():
        return None
    mtimes = [path.stat().st_mtime for path in logs_dir.glob(f"{scope_id}*.log") if path.is_file()]
    return max(mtimes) if mtimes else None


def latest_log_path(root: Path, scope_id: str) -> Path | None:
    logs_dir = root / ".agents" / "logs"
    if not logs_dir.exists():
        return None
    logs = [path for path in logs_dir.glob(f"{scope_id}*.log") if path.is_file()]
    if not logs:
        return None
    return max(logs, key=lambda path: path.stat().st_mtime)


def log_status(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {"exists": False}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"exists": True, "path": str(path), "error": str(exc)}
    lines = text.splitlines()
    useful_lines = [
        line
        for line in lines
        if line.strip()
        and not line.startswith("[watchdog] started")
        and not line.startswith("[watchdog] exited")
    ]
    exited = any(line.startswith("[watchdog] exited status=") for line in lines)
    exit_status: int | None = None
    for line in reversed(lines):
        if line.startswith("[watchdog] exited status="):
            raw_status = line.rsplit("=", 1)[-1].strip()
            try:
                exit_status = int(raw_status)
            except ValueError:
                exit_status = None
            break
    return {
        "exists": True,
        "path": str(path),
        "line_count": len(lines),
        "useful_line_count": len(useful_lines),
        "useful_hash": sha256_text("\n".join(useful_lines)) if useful_lines else "",
        "started_only": len(lines) == 1 and bool(lines and lines[0].startswith("[watchdog] started")),
        "exited": exited,
        "exit_status": exit_status,
        "updated_at": iso(dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)),
        "tail": "\n".join(lines[-6:])[-1000:],
    }


def report_path(root: Path, scope_id: str) -> Path | None:
    mapping = {
        "change-describer": root / ".agents" / "reports" / "change-summary-latest.md",
        "plan-auditor": root / ".agents" / "reports" / "plan-audit-latest.md",
    }
    return mapping.get(scope_id)


def collect_reports(root: Path) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    for key, path in {
        "change_summary": root / ".agents" / "reports" / "change-summary-latest.md",
        "plan_audit": root / ".agents" / "reports" / "plan-audit-latest.md",
    }.items():
        if path.exists():
            text = path.read_text(encoding="utf-8", errors="replace")
            reports[key] = {
                "path": str(path),
                "updated_at": iso(dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)),
                "text": text[:6000],
            }
        else:
            reports[key] = {"path": str(path), "missing": True, "text": ""}
    return reports


def collect_regression(root: Path) -> dict[str, Any]:
    path = root / ".agents" / "checks" / "latest-regression.json"
    payload = read_json(path, {})
    if not isinstance(payload, dict) or not payload:
        return {"path": str(path), "missing": True}
    payload = dict(payload)
    payload["path"] = str(path)
    return payload


def repo_status_sentence(repo_name: str, repo: dict[str, Any]) -> str:
    dirty = int(repo.get("dirty_count", 0) or 0)
    commits = repo.get("commits_last_hour") if isinstance(repo.get("commits_last_hour"), list) else []
    dirty_text = "工作区干净" if dirty == 0 else f"{dirty} 个未提交项"
    commit_text = "近一小时无新提交" if not commits else f"近一小时 {len(commits)} 个提交"
    return f"- {repo_name}: {repo.get('branch', 'unknown')} {repo.get('head', '')}，{dirty_text}，{commit_text}。"


def build_builtin_change_summary(summary: dict[str, Any]) -> str:
    repos = summary.get("repos") if isinstance(summary.get("repos"), dict) else {}
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    runtime = summary.get("runtime") if isinstance(summary.get("runtime"), dict) else {}
    godot = runtime.get("godot_linux") if isinstance(runtime.get("godot_linux"), dict) else {}
    docker = runtime.get("docker") if isinstance(runtime.get("docker"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}
    key_assignments = summary.get("key_assignments") if isinstance(summary.get("key_assignments"), dict) else {}
    regression = summary.get("regression") if isinstance(summary.get("regression"), dict) else {}

    open_pr_count = 0
    pr_sample_failures: list[str] = []
    open_pr_lines: list[str] = []
    for raw_prs in pull_requests.values():
        prs = raw_prs if isinstance(raw_prs, dict) else {}
        count = prs.get("open_count")
        if isinstance(count, int):
            open_pr_count += count
            for raw_pr in prs.get("items", []):
                pr = raw_pr if isinstance(raw_pr, dict) else {}
                open_pr_lines.append(
                    f"- {prs.get('repo')}: PR #{pr.get('number')} `{pr.get('headRefName')}` -> `{pr.get('baseRefName')}`，"
                    f"mergeState={pr.get('mergeStateStatus')}，{pr.get('url')}"
                )
        else:
            pr_sample_failures.append(str(prs.get("repo", "unknown")))

    risk_lines: list[str] = []
    if summary.get("started_count", 0):
        risk_lines.append(f"- watchdog 本轮启动了 {summary.get('started_count')} 个 fallback/持续 agent，需要观察是否正常退出并清理 lock。")
    stale_artifacts = [
        action
        for action in actions
        if isinstance(action, dict) and action.get("type") == "artifact-stale"
    ]
    for action in stale_artifacts:
        risk_lines.append(f"- {action.get('scope')} 报告/提示词未及时更新: {action.get('reason')}。")
    if regression.get("missing"):
        risk_lines.append("- 尚未找到最新回归检查 JSON，邮件只能报告环境能力，不能报告测试结果。")
    elif not regression.get("ok", False):
        failed = regression.get("failed") if isinstance(regression.get("failed"), list) else []
        names = ", ".join(str(item.get("name")) for item in failed if isinstance(item, dict))
        risk_lines.append(f"- 最新回归检查未通过: {names or 'unknown'}。")
    active_locks = [scope_id for scope_id, raw_scope in scopes.items() if isinstance(raw_scope, dict) and (raw_scope.get("lock") or {}).get("alive")]
    dead_locks = [
        scope_id
        for scope_id, raw_scope in scopes.items()
        if isinstance(raw_scope, dict) and (raw_scope.get("lock") or {}).get("dead_unfinished")
    ]
    if active_locks:
        risk_lines.append(f"- 当前仍有 active lock: {', '.join(active_locks)}。")
    if dead_locks:
        risk_lines.append(f"- watchdog 清理/发现死锁: {', '.join(dead_locks)}；旧 service 可能曾杀掉后台 agent。")
    deferred_scopes = [
        (scope_id, raw_scope.get("deferred_reason"))
        for scope_id, raw_scope in scopes.items()
        if isinstance(raw_scope, dict) and raw_scope.get("deferred")
    ]
    for scope_id, reason in deferred_scopes:
        risk_lines.append(f"- {scope_id} 本轮暂缓启动以避免同仓并发冲突: {reason}。")
    if not godot.get("exists") or not godot.get("executable"):
        risk_lines.append("- Godot Linux headless 不可用，SpellKard 运行时验证会受阻。")
    if not docker.get("available") or not docker.get("docker_compose_available"):
        risk_lines.append("- Docker 或 docker-compose 不可用，服务端容器化回归会受阻。")
    docker_files = docker.get("repo_files") if isinstance(docker.get("repo_files"), dict) else {}
    for server_repo in ("Gensoulkyo", "PhK-BattleServer"):
        if not docker_files.get(server_repo):
            risk_lines.append(f"- {server_repo} 暂未发现 Dockerfile/docker-compose 文件，只能先用本地回归。")
    missing_keys = [scope_id for scope_id, raw in key_assignments.items() if isinstance(raw, dict) and not raw.get("available")]
    if missing_keys:
        risk_lines.append(f"- 以下 scope 缺少 key alias: {', '.join(missing_keys)}。")
    if pr_sample_failures:
        risk_lines.append(f"- GitHub PR 采样失败: {', '.join(pr_sample_failures)}；不得把采样失败当成无 PR。")
    elif open_pr_count == 0:
        risk_lines.append("- 当前五个仓库没有打开的 PR；后续开发应走 feature branch + PR，不再直接推 main。")
    bugfix_actions = [action for action in actions if isinstance(action, dict) and str(action.get("type", "")).startswith("bugfix")]
    for action in bugfix_actions:
        if action.get("type") == "bugfix-pr-open":
            risk_lines.append(
                f"- SpellKard Godot 回归已有修复 PR #{action.get('number')}，mergeState={action.get('mergeStateStatus')}，等待分支保护审批/合并。"
            )
    if not risk_lines:
        risk_lines.append("- 未发现新的阻塞风险。")

    lines = [
        "## 更新前服务器状态",
        "",
        "- 已从最新 watchdog 采样生成，不再依赖上一轮 agent 手写报告。",
        "",
        "## 更新后服务器状态",
        "",
        *(repo_status_sentence(name, repo if isinstance(repo, dict) else {}) for name, repo in sorted(repos.items())),
        "",
        "## 本小时完成内容",
        "",
        f"- watchdog 已采样 manager、agent、仓库、PR、Godot Linux、Docker 和 docker-compose 状态，采样时间 {summary.get('generated_at', '')}。",
        f"- docs/ops 当前策略要求 feature branch、阶段性 commit、PR 审批流程，不再默认直接推 main。",
        f"- Godot Linux: `{godot.get('path', DEFAULT_GODOT_LINUX)}`，exists={godot.get('exists')}，executable={godot.get('executable')}，version={godot.get('version', '')}。",
        f"- Docker: available={docker.get('available')}，docker-compose={docker.get('docker_compose_available')}，version={docker.get('docker_compose_version', '')}。",
        f"- 当前 open PR 总数: {'unknown' if pr_sample_failures else open_pr_count}；PR 审批动作数: {sum(1 for action in actions if str(action.get('type', '')).startswith('pr-'))}。",
        f"- 最新回归检查: ok={regression.get('ok', 'unknown')}，failed_count={regression.get('failed_count', 'unknown')}，generated_at={regression.get('generated_at', 'missing')}。",
        "",
        "## Agent 状态",
        "",
    ]
    for scope_id, raw_scope in sorted(scopes.items()):
        scope = raw_scope if isinstance(raw_scope, dict) else {}
        lines.append(
            f"- {scope_id}: status={scope.get('status')}，repo={scope.get('repo')}，"
            f"progress={scope.get('progress')}，stalled={scope.get('stalled_count')}，"
            f"deferred={scope.get('deferred')}，lock_alive={(scope.get('lock') or {}).get('alive')}。"
        )

    lines.extend(["", "## PR 状态", ""])
    if pr_sample_failures:
        lines.append(f"- 采样失败: {', '.join(pr_sample_failures)}。")
    elif open_pr_lines:
        lines.extend(open_pr_lines)
    else:
        lines.append("- 当前未发现 open PR。")

    lines.extend(["", "## 阻塞/风险", "", *risk_lines, "", "## 下一小时建议", ""])
    lines.extend(
        [
            "- 新开发任务按 feature branch + PR 推进，并在 PR 中写明测试、风险、协议/网络/安全影响。",
            "- SpellKard 改动优先用 Linux Godot headless 跑对应 smoke/check 脚本。",
            "- 服务器无显卡导致的纯 Godot 渲染器失败可标记为 ignored/blocked；GDScript 编译、类型和脚本合同失败仍必须修复。",
            "- Gensoulkyo 与 PhK-BattleServer 优先补 Dockerfile/docker-compose 回归入口，再跑服务端回归。",
            "- watchdog 发现 PR 后应读取代码和 docs/dev 路线，满足检查才审批。",
        ]
    )
    return "\n".join(lines) + "\n"


def build_builtin_plan_audit(summary: dict[str, Any]) -> str:
    runtime = summary.get("runtime") if isinstance(summary.get("runtime"), dict) else {}
    godot = runtime.get("godot_linux") if isinstance(runtime.get("godot_linux"), dict) else {}
    docker = runtime.get("docker") if isinstance(runtime.get("docker"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}
    repos = summary.get("repos") if isinstance(summary.get("repos"), dict) else {}
    regression = summary.get("regression") if isinstance(summary.get("regression"), dict) else {}

    open_pr_count = 0
    pr_sample_failures: list[str] = []
    blocked_prs: list[str] = []
    for raw_prs in pull_requests.values():
        prs = raw_prs if isinstance(raw_prs, dict) else {}
        count = prs.get("open_count")
        if isinstance(count, int):
            open_pr_count += count
            for raw_pr in prs.get("items", []):
                pr = raw_pr if isinstance(raw_pr, dict) else {}
                if pr.get("mergeStateStatus") == "BLOCKED":
                    blocked_prs.append(f"- {prs.get('repo')}: PR #{pr.get('number')} `{pr.get('headRefName')}` 被分支保护或检查规则阻塞。")
        else:
            pr_sample_failures.append(str(prs.get("repo", "unknown")))

    direct_main_risks: list[str] = []
    for repo_name, raw_repo in sorted(repos.items()):
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        status = str(repo.get("status", ""))
        commits = repo.get("commits_last_hour") if isinstance(repo.get("commits_last_hour"), list) else []
        if repo.get("branch") == "main" and commits and not pr_sample_failures and open_pr_count == 0:
            direct_main_risks.append(f"- {repo_name}: main 分支近一小时有提交但当前没有 open PR，需要确认是否为授权 hotfix。")

    docker_files = docker.get("repo_files") if isinstance(docker.get("repo_files"), dict) else {}
    flow_risks = list(direct_main_risks)
    if pr_sample_failures:
        flow_risks.append(f"- GitHub PR 采样失败: {', '.join(pr_sample_failures)}；流程审计不能把失败当成无 PR。")
    elif open_pr_count == 0:
        flow_risks.append("- 当前无 open PR；后续开发应补齐 feature branch + PR 轨迹。")
    flow_risks.extend(blocked_prs)
    if not godot.get("exists") or not godot.get("executable"):
        flow_risks.append("- Godot Linux headless 不可用，SpellKard 阶段验证不完整。")
    if not docker.get("docker_compose_available"):
        flow_risks.append("- `docker-compose` 不可用，服务端容器回归不完整。")
    if regression.get("missing"):
        flow_risks.append("- 未找到最新 regression JSON，说明邮件与 watchdog 还缺少自动测试结果输入。")
    elif not regression.get("ok", False):
        failed = regression.get("failed") if isinstance(regression.get("failed"), list) else []
        names = ", ".join(str(item.get("name")) for item in failed if isinstance(item, dict))
        flow_risks.append(f"- 最新自动回归未通过: {names or 'unknown'}。")
    for server_repo in ("Gensoulkyo", "PhK-BattleServer"):
        if not docker_files.get(server_repo):
            flow_risks.append(f"- {server_repo}: 未发现 Dockerfile/docker-compose，服务端 Docker 回归入口仍缺失。")
    if not flow_risks:
        flow_risks.append("- 未发现当前流程阻塞。")

    return "\n".join(
        [
            "# gotouhou 持续方向与流程审计报告",
            "",
            f"审计时间：{summary.get('generated_at', '')}",
            "",
            "## 当前阶段判断",
            "",
            "- 当前仍应按 Phase 3 主线推进协议、Nakama/Go 业务服、C++ BattleServer 权威边界；SpellKard 的 UI/弹幕工作服务 Phase 2/6/8 的客户端展示、练习、Replay 和验证合同。",
            "- ops/watchdog 工作属于 Phase 6 testing/release ops，应服务调度、报告、验证和 PR 审批，不直接替代业务实现。",
            "",
            "## 符合计划的新增能力",
            "",
            "- watchdog 已采样 branch/PR、agent、Godot Linux、Docker 和 `docker-compose` 状态，邮件摘要可直接读取本轮最新报告。",
            "- worker prompt 已纳入 feature branch、阶段性 commit、PR、Linux Godot headless、服务端 Docker/`docker-compose` 回归要求。",
            "- PR 审批被定义为受控动作：读取代码和 docs/dev 路线、运行对应检查、确认无阻塞后才 `gh pr review --approve`；不自动合并。",
            "",
            "## 潜在偏离或优先级问题",
            "",
            *flow_risks,
            "",
            "## 结论",
            "",
            "- 符合：新增 ops 方向符合 Phase 6，但下一步必须把实际开发也迁移到 branch + PR 流程。",
            "- 偏离：直接推 main、无阶段 commit、无 PR、无 Godot/Docker 回归入口都应视为流程偏离并写入邮件风险。",
            "- 建议调整：manager/watchdog 继续读代码和路线后审批 PR；业务 worker 聚焦协议冻结、Nakama/数据库、C++ 真实依赖替换、SpellKard headless 运行时验证。",
            "",
            "## 建议调整的 agent 提示词",
            "",
            "- 所有开发 worker：必须从最新 `origin/main` 创建 feature branch，阶段性 commit，推分支，开 PR；PR 正文写测试、风险、协议/网络/安全影响。",
            "- SpellKard worker：必须使用 `/root/gotouhou/Godot_v4.7-stable_linux.x86_64` 运行相关 headless check。",
            "- SpellKard worker：无显卡导致的纯渲染器错误可记录为环境 blocked；GDScript parse/compile/type error 和脚本合同失败不能忽略。",
            "- 服务端 worker：优先使用 `docker-compose` 回归；缺 Dockerfile/compose 时运行本地回归并记录阻塞。",
            "- watchdog/manager：发现 open PR 后读取 diff 和 docs/dev 路线，运行 gates，通过才审批 PR；不自动合并。",
        ]
    ) + "\n"


def managed_change_describer_prompt() -> str:
    return """你是 gotouhou 持续中文摘要 agent（change-describer / Narrator）。

工作区：`/root/gotouhou`。运行模式：Codex `/goal` 持续目标模式。

每轮必须读取最新 `/root/gotouhou/.agents/last-watchdog-summary.json`，并检查五个子仓库状态、branch/PR 状态、agent roster、locks、logs、Godot Linux、Docker 与 `docker-compose` 状态。输出简单中文摘要到 `/root/gotouhou/.agents/reports/change-summary-latest.md`，同时更新本提示词文件。

摘要必须包含：更新前服务器状态、更新后服务器状态、本小时完成内容、Agent 状态、阻塞/风险、下一小时建议。

必须写入风险：报告未更新、agent lock 残留或 started-only 日志、dead lock 被清理、未走 feature branch + PR、PR 采样失败、bugfix PR 被分支保护阻塞、Godot Linux headless 未跑、服务端 Docker/`docker-compose` 回归缺失、watchdog/邮件异常、key alias 缺失。服务器无显卡导致的纯 Godot 渲染器失败可以写为 ignored/blocked，不算功能失败；GDScript parse/compile/type error、脚本加载失败和 UI/弹幕合同失败仍必须写为真实阻塞。不得泄露 SMTP 密码、token、私钥、API key 或任何凭据；可以写 key alias 和 scope，不能写 key value。只允许写 `.agents` 下指定报告和提示词，不修改 git 仓库，不提交，不推送。写报告必须原子更新：先写同目录临时文件，再 rename 替换；禁止先删除或清空现有报告。
"""


def managed_plan_auditor_prompt() -> str:
    return """你是 gotouhou 持续方向审计 agent（plan-auditor / Auditor）。

工作区：`/root/gotouhou`。运行模式：Codex `/goal` 持续目标模式。

每轮读取 `/root/gotouhou/docs/dev/progress.md` 与 `/root/gotouhou/docs/dev/gotouhou/**/*.md`，再检查五个子仓库状态、branch/PR 形态、最近提交、最新 watchdog summary、Godot Linux headless 能力、Docker/`docker-compose` 回归能力和 open PR。判断新增功能与开发流程是否符合 Phase 2/3/6/8、网络安全、Nakama、大厅/房间、C++ BattleServer、Godot UI/弹幕路线。

必须审计：是否缺阶段性 commit、是否直接推 main、是否缺 PR、PR 是否读完代码和路线后再审批、watchdog 查出的代码问题是否开独立 bugfix 分支/PR、SpellKard 是否用 Linux Godot headless 验证、服务端是否使用 Docker/`docker-compose` 或记录缺口、邮件内容是否及时反映 agent 状态和阻塞风险。started-only 日志、dead lock、报告未更新都算 agent 未正常执行，不得当成正常运行。服务器无显卡导致的纯 Godot 渲染器失败可以忽略为环境 blocked；GDScript parse/compile/type error、脚本加载失败和 UI/弹幕合同失败不能忽略。

输出 `/root/gotouhou/.agents/reports/plan-audit-latest.md`，同时更新本提示词文件。只允许写 `.agents` 下指定文件，不修改 git 仓库，不提交，不推送。不得泄露凭据。结论必须明确“符合/偏离/建议调整”，并给出可直接交给后续 worker 的中文提示词。写报告必须原子更新：先写同目录临时文件，再 rename 替换；禁止先删除或清空现有报告。
"""


def write_managed_reports(root: Path, summary: dict[str, Any]) -> None:
    reports_dir = root / ".agents" / "reports"
    prompts_dir = root / ".agents" / "agent-prompts"
    reports_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "change-summary-latest.md").write_text(build_builtin_change_summary(summary), encoding="utf-8", newline="\n")
    (reports_dir / "plan-audit-latest.md").write_text(build_builtin_plan_audit(summary), encoding="utf-8", newline="\n")
    (prompts_dir / "change-describer.md").write_text(managed_change_describer_prompt(), encoding="utf-8", newline="\n")
    (prompts_dir / "plan-auditor.md").write_text(managed_plan_auditor_prompt(), encoding="utf-8", newline="\n")


def lock_path(root: Path, scope_id: str) -> Path:
    return root / ".agents" / "locks" / f"{scope_id}.lock.json"


def lock_status(path: Path, now: dt.datetime, stale_minutes: int = 240) -> dict[str, Any]:
    payload = read_json(path, {})
    pid = payload.get("pid") if isinstance(payload, dict) else None
    unit = payload.get("unit") if isinstance(payload, dict) else None
    started = parse_iso(payload.get("started_at") if isinstance(payload, dict) else None)
    unit_active = systemd_unit_active(unit if isinstance(unit, str) else None)
    alive = pid_alive(pid if isinstance(pid, int) else None) or unit_active
    log = log_status(Path(str(payload.get("log_path"))) if isinstance(payload, dict) and payload.get("log_path") else None)
    stale = False
    age_seconds = None
    if started is not None:
        age_seconds = max(0, int((now - started).total_seconds()))
        stale = age_seconds > stale_minutes * 60
    dead_unfinished = bool(path.exists() and not alive and log.get("exists") and not log.get("exited"))
    return {
        "path": str(path),
        "exists": path.exists(),
        "pid": pid,
        "unit": unit,
        "unit_active": unit_active,
        "alive": alive,
        "stale": stale,
        "dead_unfinished": dead_unfinished,
        "age_seconds": age_seconds,
        "started_at": iso(started) if started else None,
        "log": log,
    }


def cleanup_dead_lock(path: Path, status: dict[str, Any], dry_run: bool) -> dict[str, Any] | None:
    if not status.get("exists") or status.get("alive"):
        return None
    if not (status.get("dead_unfinished") or status.get("stale")):
        return None
    action = {
        "type": "cleanup-dead-lock",
        "reason": "dead lock process with no completed watchdog exit" if status.get("dead_unfinished") else "stale lock process not alive",
        "lock": str(path),
        "lock_status": status,
        "dry_run": dry_run,
    }
    if not dry_run:
        try:
            path.unlink()
            action["removed"] = True
        except OSError as exc:
            action["removed"] = False
            action["error"] = str(exc)
    return action


def prompt_key_line(key_assignment: dict[str, Any]) -> str:
    alias = key_assignment.get("alias")
    if alias:
        return f"Assigned Codex API key alias: `{alias}`. The raw key is injected as process environment only; never print, persist, mail, or commit it."
    preferences = ", ".join(str(item) for item in key_assignment.get("preferences", []))
    return f"No matching Codex API key alias was found. Expected aliases: {preferences or '(none)'}."


def goal_prompt_preamble(scope_id: str, reason: str, key_assignment: dict[str, Any]) -> str:
    return f"""Codex /goal mode requirement:
- Treat this launch as a sustained `/goal` task, not a one-shot note.
- Keep working until the scoped objective is genuinely handled, verified, committed on a feature branch when repository files changed, pushed, and represented by a pull request.
- If interrupted, resume from local state, active locks, logs, and the latest `origin/main` without reverting others.
- Scope id: `{scope_id}`.
- Launch reason: {reason}
- {prompt_key_line(key_assignment)}
{GIT_FLOW_PROMPT}
"""


def fallback_prompt(scope_id: str, scope: dict[str, Any], reason: str, key_assignment: dict[str, Any]) -> str:
    if scope.get("kind") == "summary":
        return summary_agent_prompt(reason, key_assignment)
    if scope.get("kind") == "audit":
        return audit_agent_prompt(reason, key_assignment)

    repo = scope["repo"]
    paths = "\n".join(f"- {path}" for path in scope.get("paths", ()))
    directive = DEVELOPMENT_SCOPE_DIRECTIVES.get(scope_id, "")
    scoped_directive = f"\n上次方向审计优化后的本 scope 提示词：\n{directive}\n" if directive else ""
    return f"""{goal_prompt_preamble(scope_id, reason, key_assignment)}

You are a gotouhou fallback Codex worker for scope `{scope_id}`.

Repository root: /root/gotouhou/{repo}
Workspace root: /root/gotouhou

You are not alone in the codebase. Do not revert user or other-agent edits.
Start by syncing/rebasing from the latest `origin/main` for this repository, then inspect `git status --short --branch` and the scoped files.
Before committing or pushing, acquire the repo git lock with:
`flock /root/gotouhou/.agents/locks/git-{repo}.lock -c '<git commands>'`.

Scope summary: {scope["summary"]}
Allowed paths:
{paths}
{scoped_directive}

Implementation requirements:
- Continue the current main branch work for this scope using the optimized direction above.
- Read `/root/gotouhou/docs/dev/progress.md` and the scoped `docs/dev/gotouhou` route before coding; if the plan direction has shifted, update your PR summary and final status.
- Keep changes inside the allowed paths.
- Use UTF-8 and Linux LF.
- Run the relevant local checks for the repository.
- SpellKard scopes must use `/root/gotouhou/Godot_v4.7-stable_linux.x86_64` for Linux headless checks when touching Godot scripts/scenes/assets.
- Gensoulkyo and PhK-BattleServer scopes should prefer Docker/`docker-compose` regression where repository files exist; if no Dockerfile/compose exists, run local checks and record that Docker coverage is blocked.
- For network/protocol/server scopes, run `/root/gotouhou/docs/ops/protocol_audit_check.py`.
- Push the feature branch and create a PR. Do not push directly to `main` unless the manager explicitly authorizes an emergency hotfix.
- If watchdog/regression reveals a code failure in your scope, switch to a dedicated `fix/<area>` branch/PR first; after tests pass, request merge and report any branch protection blocker.
- Write a concise final status to `/root/gotouhou/.agents/logs/{scope_id}-final.md`.
"""


def summary_agent_prompt(reason: str, key_assignment: dict[str, Any]) -> str:
    return f"""{goal_prompt_preamble("change-describer", reason, key_assignment)}

你是 gotouhou 持续中文摘要 agent（change-describer / Narrator）。

工作区：/root/gotouhou
运行模式：Codex `/goal` 持续目标模式。每小时被 watchdog 拉起时，都要完成一次独立摘要并写回状态；异常中断后从 `.agents` 最新状态恢复。

任务：
1. 先读取最新 `/root/gotouhou/.agents/last-watchdog-summary.json`，再检查五个子仓库当前状态、最近一小时提交、branch/PR 状态、`/root/gotouhou/.agents/agent-roster.json`、locks、logs 和 reports 更新时间。
2. 检查运行环境是否变化：Godot Linux `/root/gotouhou/Godot_v4.7-stable_linux.x86_64` 是否可执行、Docker 和 `docker-compose` 是否可用、服务端仓库是否有 Dockerfile/compose。
3. 把增改功能、agent 状态、阻塞风险、运行环境和版本管理状态转写成简单中文描述，替换邮件里可读性差的原始日志。
3. 输出 `/root/gotouhou/.agents/reports/change-summary-latest.md`。
4. 同时更新 `/root/gotouhou/.agents/agent-prompts/change-describer.md`，记录你自己的最新提示词。
5. 不修改任何 git 仓库文件，不提交，不推送。

摘要格式：
- 更新前服务器状态。
- 更新后服务器状态。
- 本小时完成内容。
- 阻塞/风险。
- 下一小时建议。

写作要求：
- 不泄露 SMTP 密码、token、私钥、API key 或任何凭据。
- 可以写 key alias 和 agent scope，但不能写 key value。
- 不粘贴冗长 git 原文、diff、日志和命令输出。
- 用项目负责人能直接看懂的中文短句。
- 如果发现 watchdog 误启动、重复启动、lock 残留、报告未更新、key 分配缺失、未走分支/PR、Godot/Docker 检查缺失，必须写入风险。
- 只允许写 `.agents/reports/change-summary-latest.md` 和 `.agents/agent-prompts/change-describer.md`；不要改五个子仓库里的文件。
"""


def audit_agent_prompt(reason: str, key_assignment: dict[str, Any]) -> str:
    return f"""{goal_prompt_preamble("plan-auditor", reason, key_assignment)}

你是 gotouhou 持续方向审计 agent（plan-auditor / Auditor）。

工作区：/root/gotouhou
运行模式：Codex `/goal` 持续目标模式。每小时被 watchdog 拉起时，都要完成一次方向审计并给出后续 agent 提示词；异常中断后从 `.agents` 最新状态恢复。

任务：
1. 阅读 `/root/gotouhou/docs/dev/progress.md` 和 `/root/gotouhou/docs/dev/gotouhou/**/*.md` 中当前阶段计划，重点关注 Phase 2/3/6/8、网络安全、Nakama、大厅、C++ BattleServer、Godot UI/弹幕。
2. 检查五个子仓库 `docs`、`Gensoulkyo`、`SpellKard`、`PhK-Protocol`、`PhK-BattleServer` 的当前状态、branch/PR 形态、最近提交和最新 watchdog summary，判断新增功能是否符合计划方向。
3. 检查开发流程是否偏离：是否缺少阶段性 commit、是否直接推 main、是否缺 PR、是否缺 Godot Linux headless 或 Docker/`docker-compose` 回归。
4. 明确审计“符合/偏离/建议调整”。如果存在较大偏离，提出需要调整的 agent 方向和可直接替换的中文提示词；如果没有较大偏离，也要给出下一轮更合适的 agent 提示词。
4. 输出 `/root/gotouhou/.agents/reports/plan-audit-latest.md`。
5. 同时更新 `/root/gotouhou/.agents/agent-prompts/plan-auditor.md`，记录你自己的最新提示词。
6. 不修改任何 git 仓库文件，不提交，不推送。

审计格式：
- 当前阶段判断。
- 符合计划的新增功能。
- 潜在偏离或优先级问题。
- 建议调整的 agent 提示词：按 scope 给出可直接使用的中文提示词。

要求：
- 不泄露 SMTP 密码、token、私钥、API key 或任何凭据。
- 可以写 key alias 和 agent scope，但不能写 key value。
- 审计要覆盖 Phase 2/3/6/8、网络安全、Nakama、房间/大厅、C++ BattleServer、Godot UI/弹幕。
- 结论必须明确“符合/偏离/建议调整”。
- 提示词必须是中文，且可直接交给后续 worker 使用。
- 后续 worker 提示词必须包含分支/PR/阶段性提交、Godot Linux headless、服务端 Docker/`docker-compose` 回归和邮件状态及时更新要求。
- 最终只汇报写入路径、是否偏离、建议调整摘要。
"""


def manager_prompt(reason: str, key_assignment: dict[str, Any]) -> str:
    return f"""{goal_prompt_preamble("manager", reason, key_assignment)}

You are the gotouhou fallback manager.

Workspace root: /root/gotouhou
Mode: Codex `/goal` sustained-target mode.

Inspect `/root/gotouhou/.agents/manager-status.md`, the five child repositories,
and any active worker logs under `/root/gotouhou/.agents/logs`.
Ensure the four development scopes are covered:
- spellkard-bullet
- spellkard-ui
- gensoulkyo-lobby
- phk-battle-server

If a scope is missing, blocked, or stale, launch a scoped worker or continue the
work directly without reverting unrelated edits. Keep `/root/gotouhou/.agents`
updated. Use branch + PR flow for repository changes; do not directly push main
except for explicit emergency hotfixes authorized by the manager.

If watchdog regression finds code failures, create or monitor a dedicated
bugfix branch/PR. Once tests pass, read the PR diff and related docs/dev route,
approve when appropriate, then attempt merge only within repository policy. If
branch protection blocks merging, record the PR URL and blocker in manager
status and hourly mail.

Use the optimized direction from `/root/gotouhou/.agents/reports/plan-audit-latest.md`
when deciding the next worker prompt. Keep key values secret; state only aliases.
Make sure hourly mail content is based on the latest watchdog snapshot, locks,
reports, branch/PR state, Godot Linux availability, and Docker/`docker-compose`
test capability.
"""


def bugfix_prompt(scope_id: str, reason: str, key_assignment: dict[str, Any], failures: list[dict[str, Any]]) -> str:
    failure_lines = "\n".join(
        f"- {item.get('name')} status={item.get('status')} blocked={item.get('blocked', False)}"
        for item in failures
    )
    return f"""{goal_prompt_preamble(scope_id, reason, key_assignment)}

你是 gotouhou watchdog 代码回归修复 agent。

工作区：`/root/gotouhou/SpellKard`
分支：从最新 `origin/main` 创建或继续 `fix/godot-headless-regressions`
目标：修复 watchdog/Godot Linux headless 查出的非渲染代码回归；纯服务器无显卡导致的 renderer/RenderingDevice 失败可以标记为环境 blocked，但 GDScript parse/compile/type error、脚本加载失败、UI/弹幕合同失败必须修复。

当前失败：
{failure_lines or "- 未提供失败明细，请读取 /root/gotouhou/.agents/checks/latest-regression.json。"}

必须执行：
- 先读 `/root/gotouhou/docs/dev/progress.md`、`docs/dev/gotouhou/01_core_stg_client/bullet_pattern_system.md`、`docs/dev/gotouhou/05_content_assets_ui/ui_screens.md` 和最新 regression JSON。
- 只修改 SpellKard 中与 Godot headless 回归相关的最小文件集，不回滚他人改动。
- 使用 `/root/gotouhou/Godot_v4.7-stable_linux.x86_64` 从 `/root/gotouhou/SpellKard/godot` 运行 `../tools/client_smoke_test.gd`、`../tools/client_ui_smoke_test.gd`、`../tools/boss_pattern_catalog_check.gd` 或等价最小检查。
- 阶段性 commit，推送 bugfix 分支，创建 PR；PR 正文写明测试结果、忽略的纯渲染环境问题和未解决风险。
- 测试通过后请求合并；如果分支保护或权限阻止合并，把 PR URL 和阻塞原因写入 `/root/gotouhou/.agents/logs/{scope_id}-final.md`。
"""


def start_background_codex(
    *,
    root: Path,
    scope_id: str,
    prompt: str,
    cwd: Path,
    codex_bin: str,
    key_assignment: dict[str, Any],
    key_value: str | None,
    dry_run: bool,
    ) -> dict[str, Any]:
    now = utcnow()
    agents_dir = root / ".agents"
    locks_dir = agents_dir / "locks"
    logs_dir = agents_dir / "logs"
    prompts_dir = agents_dir / "prompts"
    run_dir = agents_dir / "run"
    lock = lock_path(root, scope_id)
    current_lock = lock_status(lock, now)
    key_alias = key_assignment.get("alias")
    if current_lock["alive"]:
        return {"started": False, "reason": "lock-active", "lock": current_lock, "key_alias": key_alias}
    cleanup_dead_lock(lock, current_lock, dry_run=dry_run)
    if dry_run:
        return {"started": False, "reason": "dry-run", "lock": current_lock, "key_alias": key_alias}
    if not key_value:
        return {
            "started": False,
            "reason": "missing-key",
            "lock": current_lock,
            "key_alias": key_alias,
            "key_preferences": key_assignment.get("preferences", []),
        }

    locks_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    prompt_path = prompts_dir / f"{scope_id}-{stamp}.txt"
    log_path = logs_dir / f"{scope_id}-{stamp}.log"
    runner_path = run_dir / f"{scope_id}-{stamp}.sh"
    prompt_path.write_text(prompt, encoding="utf-8", newline="\n")

    quoted_lock = shlex.quote(str(lock))
    quoted_log = shlex.quote(str(log_path))
    quoted_prompt = shlex.quote(str(prompt_path))
    quoted_codex = shlex.quote(codex_bin)
    quoted_cwd = shlex.quote(str(cwd))
    quoted_root = shlex.quote(str(root))
    unit = f"gotouhou-agent-{scope_id}-{stamp}".replace("_", "-").replace("/", "-")
    script = "\n".join(
        [
            "#!/bin/sh",
            "set -u",
            f"KEY_FILE={shlex.quote(str(Path(DEFAULT_KEY_FILE)))}",
            f"KEY_ALIAS={shlex.quote(str(key_alias or ''))}",
            "KEY_VALUE=$(/usr/bin/python3 - \"$KEY_FILE\" \"$KEY_ALIAS\" <<'PY'",
            "import sys",
            "key_file, wanted = sys.argv[1], sys.argv[2]",
            "with open(key_file, encoding='utf-8', errors='replace') as handle:",
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
            f"if [ -z \"$KEY_VALUE\" ]; then echo '[watchdog] missing key alias {key_alias}' >> {quoted_log}; exit 2; fi",
            "export OPENAI_API_KEY=\"$KEY_VALUE\" CODEX_API_KEY=\"$KEY_VALUE\"",
            "unset KEY_VALUE",
            f"trap 'rm -f {quoted_lock}' EXIT",
            f"echo '[watchdog] started {scope_id} at {iso(now)}' >> {quoted_log}",
            f"cd {quoted_cwd}",
            f"{quoted_codex} exec --dangerously-bypass-approvals-and-sandbox --add-dir {quoted_root} -C {quoted_cwd} - < {quoted_prompt} >> {quoted_log} 2>&1",
            "status=$?",
            f"echo '[watchdog] exited status='$status >> {quoted_log}",
            "exit $status",
        ]
    )
    runner_path.write_text(script + "\n", encoding="utf-8", newline="\n")
    runner_path.chmod(0o700)
    base_lock_payload = {
        "scope": scope_id,
        "pid": None,
        "unit": unit,
        "launcher": "pending",
        "started_at": iso(now),
        "prompt_path": str(prompt_path),
        "runner_path": str(runner_path),
        "log_path": str(log_path),
        "cwd": str(cwd),
        "key_alias": key_alias,
    }
    write_json(lock, base_lock_payload)
    try:
        if Path("/usr/bin/systemd-run").exists():
            command = [
                "/usr/bin/systemd-run",
                "--unit",
                unit,
                "--collect",
                "--property=WorkingDirectory=" + str(cwd),
                "/bin/sh",
                str(runner_path),
            ]
            code, output = run_command(command, cwd, timeout=20)
            if code != 0:
                try:
                    lock.unlink()
                except OSError:
                    pass
                return {
                    "started": False,
                    "reason": f"systemd-run-failed: {output[-1000:]}",
                    "lock": current_lock,
                    "key_alias": key_alias,
                    "unit": unit,
                }
            pid: int | None = None
            launcher = "systemd-run"
            launch_output = output[-1000:]
        else:
            process = subprocess.Popen(
                ["/bin/sh", str(runner_path)],
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=os.environ.copy(),
                start_new_session=True,
            )
            pid = process.pid
            launcher = "popen"
            launch_output = ""
    except OSError as exc:
        try:
            lock.unlink()
        except OSError:
            pass
        return {"started": False, "reason": f"spawn-failed: {exc}", "lock": current_lock, "key_alias": key_alias}

    base_lock_payload["pid"] = pid
    base_lock_payload["launcher"] = launcher
    write_json(lock, base_lock_payload)
    return {
        "started": True,
        "reason": "spawned",
        "pid": pid,
        "unit": unit,
        "launcher": launcher,
        "launch_output": launch_output,
        "prompt_path": str(prompt_path),
        "runner_path": str(runner_path),
        "log_path": str(log_path),
        "lock": str(lock),
        "key_alias": key_alias,
    }


def evaluate_scope(
    *,
    root: Path,
    scope_id: str,
    scope: dict[str, Any],
    roster_entry: dict[str, Any],
    previous: dict[str, Any] | None,
    now: dt.datetime,
    stalled_samples: int,
    same_hour: bool,
    codex_bin: str,
    key_assignment: dict[str, Any],
    key_value: str | None,
    repos: dict[str, Any],
    dry_run: bool,
) -> dict[str, Any]:
    scoped_text, diff_hash = scoped_status(root, scope)
    repo = str(scope["repo"])
    current_head = run_git(root / repo, ["rev-parse", "--short", "HEAD"]) or ""
    latest_log = latest_log_path(root, scope_id)
    log = log_status(latest_log)
    log_mtime = latest_log.stat().st_mtime if latest_log and latest_log.exists() else None
    previous_scope = ((previous or {}).get("scopes") or {}).get(scope_id, {})
    previous_repo = ((previous or {}).get("repos") or {}).get(repo, {})

    record_exists = bool(
        roster_entry.get("status") in {"running", "active", "completed", "started"}
        or roster_entry.get("agent_id")
        or roster_entry.get("last_started_at")
    )
    actions: list[dict[str, Any]] = []
    deferred = False
    deferred_reason = ""
    has_foreign_work, foreign_reason = repo_has_foreign_active_work(root, repo, scope_id, repos)
    if has_foreign_work:
        deferred = True
        deferred_reason = foreign_reason
        actions.append({"type": "scope-deferred", "scope": scope_id, "repo": repo, "reason": foreign_reason})
    lock_file = lock_path(root, scope_id)
    lock = lock_status(lock_file, now)
    cleanup_action = cleanup_dead_lock(lock_file, lock, dry_run=dry_run)
    if cleanup_action:
        actions.append(cleanup_action)
        lock = lock_status(lock_file, now)
        roster_entry["status"] = "failed"
        roster_entry["last_failure_reason"] = cleanup_action.get("reason")

    previous_log_hash = previous_scope.get("log_useful_hash")
    progress = bool(
        previous is None
        or current_head != previous_repo.get("head")
        or diff_hash != previous_scope.get("diff_hash")
        or (log.get("useful_hash") and log.get("useful_hash") != previous_log_hash)
    )
    scope_report_path = report_path(root, scope_id)
    if scope_report_path and scope_report_path.exists():
        report_mtime = scope_report_path.stat().st_mtime
        if report_mtime != previous_scope.get("report_mtime"):
            progress = True
    else:
        report_mtime = None
    recent_launch_failed = bool(lock.get("dead_unfinished"))
    fallback_log_path = roster_entry.get("fallback_log_path") if isinstance(roster_entry.get("fallback_log_path"), str) else ""
    if fallback_log_path and latest_log and Path(fallback_log_path) == latest_log and not log.get("exited"):
        recent_launch_failed = True
    if recent_launch_failed:
        progress = False

    if same_hour:
        stalled_count = int(previous_scope.get("stalled_count", 0))
    else:
        stalled_count = 0 if progress else int(previous_scope.get("stalled_count", 0)) + 1

    action_reason = ""
    should_start = False
    completed = roster_entry.get("status") == "completed"
    continuous = bool(scope.get("continuous"))
    last_started = parse_iso(roster_entry.get("last_started_at") if isinstance(roster_entry.get("last_started_at"), str) else None)
    started_this_hour = bool(last_started and hour_bucket(last_started) == hour_bucket(now))
    if deferred:
        should_start = False
    elif lock.get("alive"):
        should_start = False
    elif recent_launch_failed:
        should_start = True
        action_reason = "previous agent launch died before useful output"
    elif continuous:
        last_started = parse_iso(roster_entry.get("last_started_at") if isinstance(roster_entry.get("last_started_at"), str) else None)
        started_this_hour = bool(last_started and hour_bucket(last_started) == hour_bucket(now))
        if not started_this_hour:
            should_start = True
            action_reason = "scheduled hourly continuous scope"
        elif not progress and stalled_count >= 1:
            should_start = True
            action_reason = "continuous scope produced no useful report update"
    elif completed and not started_this_hour:
        should_start = True
        action_reason = "completed scope needs sustained /goal continuation"
    elif not record_exists:
        should_start = True
        action_reason = "missing active/completed roster record"
    elif stalled_count >= stalled_samples:
        should_start = True
        action_reason = f"stalled for {stalled_count} samples"

    if should_start:
        launch = start_background_codex(
            root=root,
            scope_id=scope_id,
            prompt=fallback_prompt(scope_id, scope, action_reason, key_assignment),
            cwd=root / repo,
            codex_bin=codex_bin,
            key_assignment=key_assignment,
            key_value=key_value,
            dry_run=dry_run,
        )
        actions.append({"type": "start-fallback-agent", "reason": action_reason, "result": launch})
        if launch.get("started"):
            roster_entry["status"] = "started"
            roster_entry["last_started_at"] = iso(now)
            roster_entry["last_start_reason"] = action_reason
            roster_entry["fallback_log_path"] = launch.get("log_path")
            roster_entry["key_alias"] = launch.get("key_alias")

    return {
        "scope": scope_id,
        "repo": repo,
        "nickname": roster_entry.get("nickname", scope.get("nickname")),
        "status": roster_entry.get("status", "unknown"),
        "record_exists": record_exists,
        "head": current_head,
        "diff_hash": diff_hash,
        "scoped_dirty": scoped_text.splitlines()[:20],
        "log_mtime": log_mtime,
        "log_useful_hash": log.get("useful_hash"),
        "log": log,
        "report_mtime": report_mtime,
        "last_seen_at": roster_entry.get("last_seen_at"),
        "progress": progress,
        "recent_launch_failed": recent_launch_failed,
        "deferred": deferred,
        "deferred_reason": deferred_reason,
        "stalled_count": stalled_count,
        "lock": lock,
        "key_alias": key_assignment.get("alias"),
        "key_available": key_assignment.get("available"),
        "actions": actions,
    }


def maybe_start_manager(
    *,
    root: Path,
    manager: dict[str, Any],
    codex_bin: str,
    key_assignment: dict[str, Any],
    key_value: str | None,
    dry_run: bool,
) -> dict[str, Any] | None:
    if not manager.get("stale"):
        return None
    age = manager.get("age_seconds")
    reason = "missing manager heartbeat" if age is None else f"manager stale for {age} seconds"
    return {
        "type": "start-manager-fallback",
        "reason": reason,
        "result": start_background_codex(
            root=root,
            scope_id="manager",
            prompt=manager_prompt(reason, key_assignment),
            cwd=root,
            codex_bin=codex_bin,
            key_assignment=key_assignment,
            key_value=key_value,
            dry_run=dry_run,
        ),
    }


def open_pr_for_branch(pull_requests: dict[str, Any], repo_name: str, branch: str) -> dict[str, Any] | None:
    repo_info = pull_requests.get(repo_name) if isinstance(pull_requests.get(repo_name), dict) else {}
    for raw_pr in repo_info.get("items", []):
        pr = raw_pr if isinstance(raw_pr, dict) else {}
        if pr.get("headRefName") == branch:
            return pr
    return None


def maybe_start_regression_bugfix(
    *,
    root: Path,
    regression: dict[str, Any],
    pull_requests: dict[str, Any],
    codex_bin: str,
    key_assignment: dict[str, Any],
    key_value: str | None,
    dry_run: bool,
) -> dict[str, Any] | None:
    failed = regression.get("failed") if isinstance(regression.get("failed"), list) else []
    spellkard_failures = [
        item
        for item in failed
        if isinstance(item, dict)
        and not item.get("blocked")
        and str(item.get("name", "")).startswith("spellkard-")
    ]
    if not spellkard_failures:
        return None
    existing_pr = open_pr_for_branch(pull_requests, "SpellKard", "fix/godot-headless-regressions")
    if existing_pr:
        return {
            "type": "bugfix-pr-open",
            "repo": "SpellKard",
            "scope": "bugfix-spellkard-godot-headless",
            "reason": "SpellKard headless regression has open bugfix PR",
            "url": existing_pr.get("url"),
            "number": existing_pr.get("number"),
            "mergeStateStatus": existing_pr.get("mergeStateStatus"),
        }
    scope_id = "bugfix-spellkard-godot-headless"
    reason = "watchdog found SpellKard non-renderer headless regression"
    return {
        "type": "start-bugfix-agent",
        "scope": scope_id,
        "repo": "SpellKard",
        "reason": reason,
        "failures": spellkard_failures,
        "result": start_background_codex(
            root=root,
            scope_id=scope_id,
            prompt=bugfix_prompt(scope_id, reason, key_assignment, spellkard_failures),
            cwd=root / "SpellKard",
            codex_bin=codex_bin,
            key_assignment=key_assignment,
            key_value=key_value,
            dry_run=dry_run,
        ),
    }


def stale_artifact_actions(root: Path, now: dt.datetime) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    prompt_names = {
        "change-describer": "change-describer.md",
        "plan-auditor": "plan-auditor.md",
    }
    for scope_id, prompt_name in prompt_names.items():
        prompt = root / ".agents" / "agent-prompts" / prompt_name
        report = report_path(root, scope_id)
        if report is None:
            continue
        if not prompt.exists():
            actions.append({"type": "artifact-stale", "scope": scope_id, "reason": "managed prompt file missing", "path": str(prompt)})
        if not report.exists():
            lock = lock_status(lock_path(root, scope_id), now)
            if lock.get("alive") and (lock.get("age_seconds") or 0) < 20 * 60:
                continue
            actions.append({"type": "artifact-stale", "scope": scope_id, "reason": "managed report file missing", "path": str(report)})
            continue
        age_seconds = max(0, int(now.timestamp() - report.stat().st_mtime))
        if age_seconds > 90 * 60:
            actions.append(
                {
                    "type": "artifact-stale",
                    "scope": scope_id,
                    "reason": f"managed report stale for {age_seconds} seconds",
                    "path": str(report),
                    "age_seconds": age_seconds,
                }
            )
    return actions


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    now = utcnow()
    current_bucket = hour_bucket(now)
    root = Path(args.root).resolve()
    agents_dir = root / ".agents"
    snapshot_dir = agents_dir / "hourly-snapshots"
    roster_path = Path(args.roster).resolve() if args.roster else agents_dir / "agent-roster.json"
    summary_path = Path(args.summary_file).resolve() if args.summary_file else agents_dir / "last-watchdog-summary.json"
    key_file = Path(args.key_file).resolve()

    if not args.dry_run:
        agents_dir.mkdir(parents=True, exist_ok=True)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

    roster = merge_roster(read_json(roster_path, {}), now)
    keyring = load_keyring(key_file)
    key_assignments = {scope_id: select_key_alias(scope_id, keyring) for scope_id in DEFAULT_SCOPES}
    key_assignments["manager"] = select_key_alias("manager", keyring)
    key_assignments["bugfix-spellkard-godot-headless"] = select_key_alias("bugfix-spellkard-godot-headless", keyring)
    latest_snapshot = load_previous_snapshot(snapshot_dir)
    previous = load_previous_distinct_snapshot(snapshot_dir, current_bucket) or latest_snapshot
    same_hour = bool(latest_snapshot and snapshot_bucket(latest_snapshot) == current_bucket)
    repos = {name: collect_repo(root, name, now) for name in DEFAULT_REPOS}
    manager = collect_manager(root, now, args.manager_stale_minutes)
    systemd_mail = collect_systemd_mail(now)
    runtime = collect_runtime_environment(root, now, Path(args.godot_bin).resolve())
    pull_requests = collect_pull_requests(root, now)
    regression = collect_regression(root)
    actions: list[dict[str, Any]] = []
    manager_action = maybe_start_manager(
        root=root,
        manager=manager,
        codex_bin=args.codex_bin,
        key_assignment=key_assignments["manager"],
        key_value=selected_key_value(key_assignments["manager"], keyring),
        dry_run=args.dry_run,
    )
    if manager_action:
        actions.append(manager_action)

    scopes: dict[str, Any] = {}
    for scope_id, scope in DEFAULT_SCOPES.items():
        entry = roster["scopes"].setdefault(scope_id, {})
        key_assignment = key_assignments[scope_id]
        scopes[scope_id] = evaluate_scope(
            root=root,
            scope_id=scope_id,
            scope=scope,
            roster_entry=entry,
            previous=previous,
            now=now,
            stalled_samples=args.stalled_samples,
            same_hour=same_hour,
            codex_bin=args.codex_bin,
            key_assignment=key_assignment,
            key_value=selected_key_value(key_assignment, keyring),
            repos=repos,
            dry_run=args.dry_run,
        )
        entry["last_seen_at"] = iso(now)
        entry["last_head"] = scopes[scope_id]["head"]
        entry["last_diff_hash"] = scopes[scope_id]["diff_hash"]
        entry["last_stalled_count"] = scopes[scope_id]["stalled_count"]
        entry["key_alias"] = key_assignment.get("alias")
        actions.extend(scopes[scope_id]["actions"])

    reports = collect_reports(root)
    bugfix_action = maybe_start_regression_bugfix(
        root=root,
        regression=regression,
        pull_requests=pull_requests,
        codex_bin=args.codex_bin,
        key_assignment=key_assignments["bugfix-spellkard-godot-headless"],
        key_value=selected_key_value(key_assignments["bugfix-spellkard-godot-headless"], keyring),
        dry_run=args.dry_run,
    )
    if bugfix_action:
        actions.append(bugfix_action)

    actions.extend(maybe_approve_pull_requests(root, pull_requests, args.approve_prs))
    actions.extend(stale_artifact_actions(root, now))
    summary = {
        "version": 1,
        "generated_at": iso(now),
        "hour_bucket": current_bucket,
        "root": str(root),
        "dry_run": bool(args.dry_run),
        "manager": manager,
        "keyring": keyring_public_summary(keyring),
        "key_assignments": key_assignments,
        "systemd_mail": systemd_mail,
        "runtime": runtime,
        "pull_requests": pull_requests,
        "reports": reports,
        "regression": regression,
        "repos": repos,
        "scopes": scopes,
        "actions": actions,
        "action_count": len(actions),
        "started_count": sum(1 for action in actions if (action.get("result") or {}).get("started")),
        "failures": [
            action
            for action in actions
            if action.get("result") and not action["result"].get("started") and action["result"].get("reason") != "dry-run"
        ],
        "summary_path": str(summary_path),
        "roster_path": str(roster_path),
    }

    if not args.dry_run:
        write_managed_reports(root, summary)
        summary["reports"] = collect_reports(root)
        snapshot_path = snapshot_dir / f"{now.strftime('%Y%m%dT%H%M%SZ')}.json"
        write_json(snapshot_path, summary)
        summary["snapshot_path"] = str(snapshot_path)
        roster["last_summary_path"] = str(summary_path)
        roster["last_snapshot_path"] = str(snapshot_path)
        write_json(roster_path, roster)
        write_json(summary_path, summary)
        write_manager_files(root, summary, now)

    return summary


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/root/gotouhou")
    parser.add_argument("--summary-file", default="")
    parser.add_argument("--roster", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--manager-stale-minutes", type=int, default=90)
    parser.add_argument("--stalled-samples", type=int, default=2)
    parser.add_argument("--codex-bin", default=os.getenv("CODEX_BIN", "/root/.local/bin/codex"))
    parser.add_argument("--key-file", default=os.getenv("CODEX_AGENT_KEYS", DEFAULT_KEY_FILE))
    parser.add_argument("--godot-bin", default=os.getenv("GOTOUHOU_GODOT_BIN", DEFAULT_GODOT_LINUX))
    parser.add_argument("--approve-prs", action="store_true", default=os.getenv("GOTOUHOU_WATCHDOG_APPROVE_PRS") == "1")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    summary = build_summary(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
