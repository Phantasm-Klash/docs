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
ACTIVE_STARTED_ONLY_STALL_SECONDS = 10 * 60
ACTIVE_NO_PROGRESS_STALL_SECONDS = 20 * 60
BUGFIX_SCOPE_PREFIX = "bugfix-"

KEY_ALIAS_PREFERENCES: dict[str, tuple[str, ...]] = {
    "spellkard-bullet": ("spellkard-bullet", "spellkard", "other"),
    "spellkard-ui": ("spellkard-ui", "spellkard", "other"),
    "gensoulkyo-lobby": ("gensoulkyo-lobby", "gensoulkyo", "other"),
    "phk-battle-server": ("phk-battle-server", "phk", "battle-server", "battle", "other"),
    "change-describer": ("change-describer", "docs", "ops", "other"),
    "plan-auditor": ("plan-auditor", "docs", "ops", "other"),
    "bugfix-spellkard-godot-headless": ("spellkard-ui", "spellkard-bullet", "spellkard", "other"),
    "bugfix-gensoulkyo-regression": ("gensoulkyo-lobby", "gensoulkyo", "other"),
    "bugfix-phk-battle-server-regression": ("phk-battle-server", "phk", "battle-server", "battle", "other"),
    "bugfix-phk-protocol-regression": ("phk-protocol", "protocol", "phk", "other"),
    "bugfix-protocol-audit-regression": ("phk", "protocol", "gensoulkyo", "battle-server", "other"),
    "manager": ("manager", "ops", "other"),
}

BUGFIX_FAILURE_ROUTES: dict[str, dict[str, Any]] = {
    "spellkard-client-ui-headless": {
        "scope": "bugfix-spellkard-godot-headless",
        "repo": "SpellKard",
        "branch": "fix/godot-headless-regressions",
        "kind": "spellkard-godot",
    },
    "spellkard-boss-pattern-headless": {
        "scope": "bugfix-spellkard-godot-headless",
        "repo": "SpellKard",
        "branch": "fix/godot-headless-regressions",
        "kind": "spellkard-godot",
    },
    "gensoulkyo-docker-compose": {
        "scope": "bugfix-gensoulkyo-regression",
        "repo": "Gensoulkyo",
        "branch": "fix/gensoulkyo-regression",
        "kind": "server",
    },
    "battle-server-docker-compose": {
        "scope": "bugfix-phk-battle-server-regression",
        "repo": "PhK-BattleServer",
        "branch": "fix/battle-server-regression",
        "kind": "server",
    },
    "cross-repo-protocol-audit": {
        "scope": "bugfix-protocol-audit-regression",
        "repo": "docs",
        "branch": "fix/protocol-audit-regression",
        "kind": "protocol",
    },
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
- 每次最终状态和邮件必须来自补救动作后的最新采样；不能把启动前的旧 lock/unit/PR 状态当作最终状态。
- 连续样本无 scope 路径 commit 指纹、scoped diff、有效日志、report/final 状态更新、scope 专属 heartbeat 或测试指纹变化的 agent 算停滞；同仓其他 scope 的 repo HEAD 变化不能算本 scope 进展，只有 `[watchdog] started` 的日志不能算正常运行。
- systemd fallback runner 会固定 `HOME=/root`、`XDG_CONFIG_HOME=/root/.config`、`GH_CONFIG_DIR=/root/.config/gh`，继承 GitHub CLI credential helper，并设置 GitHub socks 代理；如果推送或 PR 创建仍失败，必须写入 final log 和邮件风险，不得假报完成。
- `codex exec` fallback 是按轮次完成后退出的执行器，不是常驻 daemon；日志出现 `[watchdog] exited status=0` 且 systemd unit 不活跃时，应记录为 completed/idle，不能继续显示 started/running。非零退出必须记录 failed 并进入补救判断。
- 不得把全局 manager heartbeat 或整点全局 regression 文件 mtime 当作某个 scope 的推进信号。
"""


DEFAULT_SCOPES: dict[str, dict[str, Any]] = {
    "spellkard-bullet": {
        "nickname": "Mendel",
        "agent_id": "019f0e84-8d8d-7510-be5e-abd7c4dd2b16",
        "repo": "SpellKard",
        "continuous": True,
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
        "continuous": True,
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
        "continuous": True,
        "paths": (
            "cmd/gensoulkyo_nakama",
            "dev/progress.md",
            "Dockerfile",
            "docker-compose.yml",
            "migrations",
            "runtime/core",
            "runtime/nakamaapi",
        ),
        "summary": "Nakama lobby lifecycle and security",
    },
    "phk-battle-server": {
        "nickname": "Franklin",
        "agent_id": "019f0e86-2176-7da2-98bb-495334d778f2",
        "repo": "PhK-BattleServer",
        "continuous": True,
        "paths": (
            "dev/progress.md",
            "Dockerfile",
            "docker-compose.yml",
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
    env.setdefault("GH_CONFIG_DIR", "/root/.config/gh")
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


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8", newline="\n")
    tmp_path.replace(path)


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
    public_error = "read-error" if keyring.get("error") else None
    return {
        "source": "configured-local-keyring",
        "exists": bool(keyring.get("exists")),
        "aliases": sorted(str(alias) for alias in aliases),
        "alias_count": len(aliases),
        "permissions": keyring.get("permissions"),
        "permission_warning": bool(keyring.get("permission_warning")),
        "error": public_error,
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


def systemd_unit_info(unit: str | None) -> dict[str, Any]:
    if not unit:
        return {"unit": None, "active": False, "exists": False}
    active_code, active_output = run_command(["systemctl", "is-active", unit], Path("/"), timeout=10)
    show_code, show_output = run_command(
        ["systemctl", "show", unit, "--property=ActiveState,SubState,MainPID,LoadState", "--no-pager"],
        Path("/"),
        timeout=10,
    )
    fields: dict[str, str] = {}
    if show_code == 0:
        for line in show_output.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                fields[key] = value
    main_pid: int | None = None
    try:
        parsed_pid = int(fields.get("MainPID", "0"))
        if parsed_pid > 1:
            main_pid = parsed_pid
    except ValueError:
        main_pid = None
    load_state = fields.get("LoadState", "")
    active_state = fields.get("ActiveState", active_output.strip())
    return {
        "unit": unit,
        "exists": show_code == 0 and load_state not in {"", "not-found"},
        "active": active_code == 0 and active_output.strip() == "active",
        "active_state": active_state,
        "sub_state": fields.get("SubState", ""),
        "load_state": load_state,
        "main_pid": main_pid,
        "main_pid_alive": pid_alive(main_pid),
        "is_active_status": active_code,
        "show_status": show_code,
        "is_active_output": active_output,
    }


def systemd_unit_active(unit: str | None) -> bool:
    return bool(systemd_unit_info(unit).get("active"))


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


def scoped_head_fingerprint(root: Path, scope: dict[str, Any]) -> dict[str, Any]:
    repo = root / str(scope["repo"])
    paths = [str(path) for path in scope.get("paths", ())]
    repo_head = run_git(repo, ["rev-parse", "--short", "HEAD"]) or ""
    if not paths:
        return {
            "head": repo_head,
            "repo_head": repo_head,
            "commit": repo_head,
            "fingerprint": repo_head,
            "paths": [],
            "source": "repo-head-no-scope-paths",
        }

    latest_commit = run_git(repo, ["log", "-1", "--format=%H", "--", *paths])
    latest_short = run_git(repo, ["log", "-1", "--format=%h", "--", *paths])
    tree_state = run_git(repo, ["ls-tree", "-r", "HEAD", "--", *paths], timeout=30)
    fingerprint_payload = "\n".join([latest_commit, tree_state])
    fingerprint = sha256_text(fingerprint_payload)
    return {
        "head": latest_short or latest_commit[:12] or repo_head,
        "repo_head": repo_head,
        "commit": latest_commit,
        "fingerprint": fingerprint,
        "paths": paths,
        "source": "scoped-paths",
    }


def scoped_commit_progress(previous: dict[str, Any] | None, previous_scope: dict[str, Any], current_head: str, current_fingerprint: str) -> bool:
    if previous is None:
        return True
    previous_fingerprint = previous_scope.get("head_fingerprint")
    if previous_fingerprint:
        return current_fingerprint != previous_fingerprint
    return current_head != previous_scope.get("head")


def collect_pr_list(root: Path, repo_name: str, state: str, now: dt.datetime, limit: int = 20) -> dict[str, Any]:
    command = [
        "gh",
        "pr",
        "list",
        "--repo",
        f"{GITHUB_ORG}/{repo_name}",
        "--state",
        state,
        "--limit",
        str(limit),
        "--json",
        "number,title,headRefName,baseRefName,author,isDraft,mergeStateStatus,url,updatedAt,mergedAt",
    ]
    repo_root = root / repo_name
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
        return {
            "repo": repo_name,
            "state": state,
            "count": len(payload),
            "items": payload[:limit],
            "collected_at": iso(now),
            "status": code,
        }
    return {
        "repo": repo_name,
        "state": state,
        "count": None,
        "items": [],
        "error": f"gh pr list --state {state} failed or returned invalid JSON",
        "status": code,
        "output_tail": (output + ("\nfallback:\n" + fallback_output if fallback_output else ""))[-1000:],
        "collected_at": iso(now),
    }


def collect_pull_requests(root: Path, now: dt.datetime) -> dict[str, Any]:
    repos: dict[str, Any] = {}
    for repo_name in DEFAULT_REPOS:
        open_info = collect_pr_list(root, repo_name, "open", now)
        merged_info = collect_pr_list(root, repo_name, "merged", now, limit=10)
        if open_info.get("count") is not None:
            repos[repo_name] = {
                "repo": repo_name,
                "open_count": open_info.get("count"),
                "items": open_info.get("items", []),
                "recent_merged_count": merged_info.get("count"),
                "recent_merged_items": merged_info.get("items", [])[:10],
                "collected_at": iso(now),
                "status": open_info.get("status"),
                "merged_status": merged_info.get("status"),
            }
        else:
            repos[repo_name] = {
                "repo": repo_name,
                "open_count": None,
                "items": [],
                "recent_merged_count": merged_info.get("count"),
                "recent_merged_items": merged_info.get("items", [])[:10],
                "error": open_info.get("error"),
                "status": open_info.get("status"),
                "output_tail": open_info.get("output_tail"),
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
    if repo_name == "docs" and scope_id in {"change-describer", "plan-auditor"}:
        return False, ""
    if branch.startswith(f"agent/{scope_id}/"):
        return False, ""
    if branch.startswith("agent/") and not branch.startswith(f"agent/{scope_id}/"):
        return True, f"{repo_name} is on branch {branch} owned by another scope; defer {scope_id}"
    if branch.startswith("fix/"):
        return True, f"{repo_name} is on bugfix branch {branch}; defer normal scope {scope_id}"
    if dirty_count <= 0:
        return False, ""
    if branch.startswith("fix/"):
        return True, f"{repo_name} is on dirty bugfix branch {branch}; defer normal scope {scope_id}"
    return True, f"{repo_name} has uncommitted work on {branch}; defer {scope_id}"


def scope_ids_for_repo(repo_name: str) -> list[str]:
    return [scope_id for scope_id, scope in DEFAULT_SCOPES.items() if scope.get("repo") == repo_name]


def repo_has_active_scope_lock(root: Path, repo_name: str, scope_id: str, now: dt.datetime) -> tuple[bool, str]:
    for other_scope_id in scope_ids_for_repo(repo_name):
        if other_scope_id == scope_id:
            continue
        status = lock_status(lock_path(root, other_scope_id), now)
        if status.get("alive"):
            return True, f"{repo_name} has active scope lock {other_scope_id}; defer {scope_id}"
    return False, ""


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


def docs_route_paths_for_repo(repo_name: str) -> tuple[str, ...]:
    common = ("dev/progress.md", "dev/gotouhou/00_overview/network_security_and_server_split_plan.md")
    if repo_name == "SpellKard":
        return (
            *common,
            "dev/gotouhou/01_core_stg_client/bullet_pattern_system.md",
            "dev/gotouhou/05_content_assets_ui/ui_screens.md",
        )
    if repo_name == "Gensoulkyo":
        return (
            *common,
            "dev/gotouhou/04_server_database_economy/server_stack.md",
            "dev/gotouhou/04_server_database_economy/client_server_connection.md",
        )
    if repo_name == "PhK-BattleServer":
        return (
            *common,
            "dev/gotouhou/02_networked_match/deterministic_lockstep_review.md",
            "dev/gotouhou/08_game_modes/mode_shared_server_interfaces.md",
        )
    if repo_name == "PhK-Protocol":
        return (
            *common,
            "dev/gotouhou/02_networked_match/deterministic_lockstep_review.md",
            "dev/gotouhou/08_game_modes/mode_shared_server_interfaces.md",
        )
    return common


def pr_review_evidence(root: Path, repo_name: str, pr: dict[str, Any]) -> dict[str, Any]:
    number = pr.get("number")
    diff_status = 1
    diff_output = ""
    if isinstance(number, int):
        diff_status, diff_output = run_command(
            ["gh", "pr", "diff", str(number), "--repo", f"{GITHUB_ORG}/{repo_name}"],
            root / repo_name,
            timeout=60,
            env=gh_env(),
        )
    route_files: list[dict[str, Any]] = []
    docs_root = root / "docs"
    for rel_path in docs_route_paths_for_repo(repo_name):
        path = docs_root / rel_path
        if not path.exists():
            route_files.append({"path": str(path), "exists": False})
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            route_files.append({"path": str(path), "exists": True, "error": str(exc)})
            continue
        route_files.append(
            {
                "path": str(path),
                "exists": True,
                "sha256": sha256_text(text),
                "bytes": len(text.encode("utf-8")),
            }
        )
    return {
        "diff_status": diff_status,
        "diff_bytes": len(diff_output.encode("utf-8")) if diff_output else 0,
        "diff_sha256": sha256_text(diff_output) if diff_output else "",
        "diff_excerpt": diff_output[:1200],
        "docs_routes": route_files,
    }


def pr_approval_checks(root: Path, repo_name: str, pr: dict[str, Any]) -> dict[str, Any]:
    blockers: list[str] = []
    evidence = pr_review_evidence(root, repo_name, pr)
    if evidence.get("diff_status") != 0 or not evidence.get("diff_sha256"):
        blockers.append("PR diff could not be read before approval")
    missing_routes = [
        route.get("path")
        for route in evidence.get("docs_routes", [])
        if isinstance(route, dict) and not route.get("exists")
    ]
    if missing_routes:
        blockers.append(f"docs/dev route missing: {', '.join(str(path) for path in missing_routes[:3])}")
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
    return {"blockers": blockers, "evidence": evidence}


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
            check_result = pr_approval_checks(root, repo_name, pr)
            blockers = check_result.get("blockers") if isinstance(check_result.get("blockers"), list) else []
            if blockers:
                actions.append(
                    {
                        "type": "pr-approval-skipped",
                        "repo": repo_name,
                        "number": number,
                        "url": pr.get("url"),
                        "blockers": blockers,
                        "evidence": check_result.get("evidence"),
                    }
                )
                continue
            body = (
                "watchdog route/code review passed: PR diff was read, docs/dev direction "
                "was sampled, local regression gates completed, and no blocking PR metadata "
                "was found."
            )
            code, output = run_command(
                ["gh", "pr", "review", str(number), "--repo", f"{GITHUB_ORG}/{repo_name}", "--approve", "--body", body],
                root / repo_name,
                timeout=60,
                env=gh_env(),
            )
            actions.append(
                {
                    "type": "pr-approved" if code == 0 else "pr-approval-failed",
                    "repo": repo_name,
                    "number": number,
                    "url": pr.get("url"),
                    "status": code,
                    "output": output[-1000:],
                    "evidence": check_result.get("evidence"),
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
        "Key policy: agents receive per-scope keys from the configured local keyring; status files record aliases only.",
        "Version policy: development work uses feature branches, staged commits, pull requests, and protected-main reviews by default.",
        f"Godot Linux: {godot.get('path', DEFAULT_GODOT_LINUX)} exists={godot.get('exists')} executable={godot.get('executable')} version={godot.get('version', '')}",
        f"Docker: available={docker.get('available')} docker-compose={docker.get('docker_compose_available')} version={docker.get('docker_compose_version', '')}",
        "",
        "## Managed goal scopes",
        "",
        "| Scope | Repo | Status | Key alias | continuous | started_this_hour | due_for_continuation | Deferred | Progress | Stalled | Head | Actions |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scope_id, raw_scope in sorted(scopes.items()):
        scope = raw_scope if isinstance(raw_scope, dict) else {}
        key_assignment = key_assignments.get(scope_id) if isinstance(key_assignments.get(scope_id), dict) else {}
        lines.append(
            "| "
            f"{scope_id} | {scope.get('repo', '')} | {scope.get('status', '')} | "
            f"{key_assignment.get('alias') or '(missing)'} | "
            f"{scope.get('continuous', '')} | "
            f"{scope.get('started_this_hour', '')} | "
            f"{scope.get('due_for_continuation', '')} | "
            f"{scope.get('deferred', '')} | "
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
            "- The four development scopes plus the two reporting scopes are continuous `/goal` scopes; once the hourly bucket changes, completed scopes are relaunched unless an active same-repo lock or foreign branch would make that unsafe.",
            "- Missing scopes, stale manager heartbeat, failed launches, and due continuous scopes start a fallback `codex exec` worker.",
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


def test_log_mtime(root: Path, scope_id: str, repo_name: str) -> float | None:
    agents_dir = root / ".agents"
    candidates: list[Path] = []
    logs_dir = agents_dir / "logs"
    if logs_dir.exists():
        for pattern in (f"{scope_id}*test*.log", f"{scope_id}*check*.log", f"{repo_name}*test*.log", f"{repo_name}*check*.log"):
            candidates.extend(path for path in logs_dir.glob(pattern) if path.is_file())
    return newest_file_mtime(candidates)


def scope_heartbeat_mtime(root: Path, scope_id: str) -> float | None:
    candidates = [
        root / ".agents" / "heartbeats" / f"{scope_id}.json",
        root / ".agents" / f"{scope_id}-heartbeat.json",
    ]
    return newest_file_mtime(candidates)


def scope_check_names(scope_id: str, repo_name: str) -> tuple[str, ...]:
    if scope_id == "spellkard-ui":
        return ("spellkard-client-ui-headless",)
    if scope_id == "spellkard-bullet":
        return ("spellkard-boss-pattern-headless",)
    if scope_id == "gensoulkyo-lobby":
        return ("gensoulkyo-docker-compose", "cross-repo-protocol-audit")
    if scope_id == "phk-battle-server":
        return ("battle-server-docker-compose", "cross-repo-protocol-audit")
    if repo_name == "PhK-Protocol":
        return ("cross-repo-protocol-audit",)
    return ()


def scope_test_signal(root: Path, scope_id: str, repo_name: str) -> str:
    parts: list[str] = []
    mtime = test_log_mtime(root, scope_id, repo_name)
    if mtime is not None:
        parts.append(f"log_mtime={int(mtime)}")
    regression = collect_regression(root)
    checks = regression.get("checks") if isinstance(regression.get("checks"), list) else []
    wanted_names = set(scope_check_names(scope_id, repo_name))
    for raw_check in checks:
        check = raw_check if isinstance(raw_check, dict) else {}
        name = str(check.get("name", ""))
        if name not in wanted_names:
            continue
        parts.append(
            json.dumps(
                {
                    "name": name,
                    "ok": check.get("ok"),
                    "status": check.get("status"),
                    "output_tail": check.get("output_tail", ""),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return sha256_text("\n".join(parts)) if parts else ""


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
    started_only = bool(lines) and not useful_lines and not any(line.startswith("[watchdog] exited status=") for line in lines)
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
        "started_only": started_only,
        "exited": exited,
        "exit_status": exit_status,
        "updated_at": iso(dt.datetime.fromtimestamp(path.stat().st_mtime, UTC)),
        "tail": "\n".join(lines[-6:])[-1000:],
    }


def log_has_useful_output(log: dict[str, Any]) -> bool:
    return bool(log.get("useful_hash") and int(log.get("useful_line_count", 0) or 0) > 0)


def log_finished_successfully(log: dict[str, Any]) -> bool:
    return bool(log.get("exited") and log.get("exit_status") == 0)


def log_finished_with_failure(log: dict[str, Any]) -> bool:
    return bool(log.get("exited") and log.get("exit_status") != 0)


def active_lock_stall_reason(lock: dict[str, Any], log: dict[str, Any], progress: bool) -> str:
    if not lock.get("alive"):
        return ""
    age_seconds = int(lock.get("age_seconds", 0) or 0)
    if log.get("started_only") and age_seconds >= ACTIVE_STARTED_ONLY_STALL_SECONDS:
        return f"active lock has only watchdog started output for {age_seconds} seconds"
    if not log_has_useful_output(log) and age_seconds >= ACTIVE_NO_PROGRESS_STALL_SECONDS:
        return f"active lock has no useful output for {age_seconds} seconds"
    if not progress and age_seconds >= ACTIVE_NO_PROGRESS_STALL_SECONDS:
        return f"active lock has no scoped progress for {age_seconds} seconds"
    return ""


def shell_export_line(name: str, value: str) -> str:
    return f"export {name}={shlex.quote(value)}"


def runtime_log_for_roster(roster_entry: dict[str, Any], latest_log: Path | None) -> tuple[dict[str, Any], Path | None]:
    fallback_log_path = roster_entry.get("fallback_log_path")
    if isinstance(fallback_log_path, str) and fallback_log_path:
        path = Path(fallback_log_path)
        return log_status(path), path
    return log_status(latest_log), latest_log


def reconcile_roster_exit_status(
    roster_entry: dict[str, Any],
    *,
    current_head: str,
    lock: dict[str, Any],
    runtime_log: dict[str, Any],
    now: dt.datetime,
) -> None:
    """Reflect finished fallback processes in the roster instead of leaving them as started."""
    if lock.get("alive") or not runtime_log.get("exited"):
        return
    status = str(roster_entry.get("status", ""))
    if status not in {"started", "running", "active"}:
        return
    exit_status = runtime_log.get("exit_status")
    exited_at = str(runtime_log.get("updated_at") or iso(now))
    roster_entry["last_exit_status"] = exit_status
    roster_entry["last_exited_at"] = exited_at
    if exit_status == 0:
        roster_entry["status"] = "completed"
        roster_entry["completed_at"] = exited_at
        roster_entry["completed_commit"] = current_head
        roster_entry.pop("last_failure_reason", None)
    else:
        roster_entry["status"] = "failed"
        roster_entry["last_failure_reason"] = f"fallback exited with status {exit_status}"


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


def scope_risk_reason(scope_id: str, scope: dict[str, Any]) -> str:
    lock = scope.get("lock") if isinstance(scope.get("lock"), dict) else {}
    log = scope.get("log") if isinstance(scope.get("log"), dict) else {}
    reasons: list[str] = []
    if lock.get("stale"):
        reasons.append("lock 已超过保守时限")
    if lock.get("dead_unfinished"):
        reasons.append("lock 对应进程/unit 已死且日志没有正常退出记录")
    if lock.get("alive") and not log_has_useful_output(log):
        reasons.append("agent 已启动但日志仍无有效输出")
    if scope.get("report_expected") and not scope.get("report_updated"):
        reasons.append("受管报告 mtime 未更新")
    stalled_count = int(scope.get("stalled_count", 0) or 0)
    if stalled_count >= 2:
        reasons.append("连续两次没有 scoped diff、commit、scope heartbeat 或测试指纹变化")
    elif not scope.get("progress"):
        reasons.append("本轮没有 scoped diff、commit、scope heartbeat 或测试指纹变化")
    if scope.get("recent_launch_failed"):
        reasons.append("上次补救启动未产生有效输出")
    active_stall_reason = (scope.get("stall_signals") or {}).get("active_stall_reason")
    if active_stall_reason:
        reasons.append(str(active_stall_reason))
    if not reasons:
        return ""
    return f"{scope_id}: " + "；".join(reasons)


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
    merged_pr_lines: list[str] = []
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
            for raw_pr in prs.get("recent_merged_items", [])[:3]:
                pr = raw_pr if isinstance(raw_pr, dict) else {}
                merged_pr_lines.append(
                    f"- {prs.get('repo')}: merged PR #{pr.get('number')} `{pr.get('headRefName')}` -> `{pr.get('baseRefName')}`，"
                    f"mergedAt={pr.get('mergedAt')}，{pr.get('url')}"
                )
        else:
            pr_sample_failures.append(str(prs.get("repo", "unknown")))

    risk_lines: list[str] = []
    if summary.get("started_count", 0):
        risk_lines.append(f"- watchdog 本轮启动了 {summary.get('started_count')} 个 fallback/持续 agent，需要观察是否正常退出并清理 lock。")
    continuous_waiting = [
        scope_id
        for scope_id, raw_scope in scopes.items()
        if isinstance(raw_scope, dict)
        and raw_scope.get("continuous")
        and raw_scope.get("due_for_continuation")
        and not raw_scope.get("deferred")
        and not (raw_scope.get("lock") or {}).get("alive")
    ]
    if continuous_waiting:
        risk_lines.append(
            "- 以下持续 `/goal` scope 已到补位时间但本轮未启动，需要检查同小时限流或启动动作: "
            + ", ".join(sorted(continuous_waiting))
            + "。"
        )
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
    for scope_id, raw_scope in sorted(scopes.items()):
        if not isinstance(raw_scope, dict):
            continue
        risk_reason = scope_risk_reason(scope_id, raw_scope)
        if risk_reason:
            risk_lines.append(f"- 停滞风险: {risk_reason}。")
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
    elif open_pr_count == 0 and not merged_pr_lines:
        risk_lines.append("- 当前五个仓库没有打开的 PR，且未采样到最近 merged PR；后续开发应走 feature branch + PR，不再直接推 main。")
    bugfix_actions = [action for action in actions if isinstance(action, dict) and str(action.get("type", "")).startswith("bugfix")]
    for action in bugfix_actions:
        if action.get("type") == "bugfix-pr-open":
            risk_lines.append(
                f"- {action.get('repo')} 回归已有修复 PR #{action.get('number')}，mergeState={action.get('mergeStateStatus')}，等待分支保护审批/合并。"
            )
        elif action.get("type") == "bugfix-deferred":
            risk_lines.append(f"- {action.get('repo')} 回归修复 agent 暂缓: {action.get('reason')}。")
    started_bugfix = [action for action in actions if isinstance(action, dict) and action.get("type") == "start-bugfix-agent"]
    for action in started_bugfix:
        result = action.get("result") if isinstance(action.get("result"), dict) else {}
        risk_lines.append(
            f"- watchdog 已为 {action.get('repo')} 回归启动独立 bugfix agent `{action.get('scope')}`，"
            f"started={result.get('started')}，branch={action.get('branch')}。"
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
        "- agent 停滞判定已使用 scope 路径 commit 指纹，不再把同仓其他 scope 的 repo HEAD 变化误算为本 scope 进展。",
        "- 四个开发 scope 与两个报告/审计 scope 均按持续 `/goal` scope 管理；每个新小时会补位拉起，若同仓有活动锁或外来分支则暂缓。",
        "- 历史漏检原因已定位：旧逻辑把同仓 repo HEAD、全局 heartbeat 和过宽的日志输出算作 scope 进展；现在只有 scope 路径提交、scoped diff、scope heartbeat、有效报告/测试/日志变化才算推进。",
        "- watchdog 发现回归失败时会按检查类型启动独立 bugfix agent：SpellKard headless、Gensoulkyo docker-compose、PhK-BattleServer docker-compose、跨仓协议审计分别走独立 fix 分支和 PR。",
        "- fallback runner 已固定 `/root` GitHub CLI 配置、credential helper、socks 代理和 Go cache；worker 本地提交后应直接推分支并开 PR。",
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
            f"continuous={scope.get('continuous')}，started_hour={scope.get('started_this_hour')}，"
            f"continue_due={scope.get('due_for_continuation')}，progress={scope.get('progress')}，stalled={scope.get('stalled_count')}，"
            f"deferred={scope.get('deferred')}，lock_alive={(scope.get('lock') or {}).get('alive')}。"
        )

    lines.extend(["", "## PR 状态", ""])
    if pr_sample_failures:
        lines.append(f"- 采样失败: {', '.join(pr_sample_failures)}。")
    elif open_pr_lines:
        lines.extend(open_pr_lines)
        if merged_pr_lines:
            lines.extend(["", "最近已合并 PR:", *merged_pr_lines[:10]])
    elif merged_pr_lines:
        lines.extend(["- 当前未发现 open PR。", "", "最近已合并 PR:", *merged_pr_lines[:10]])
    else:
        lines.append("- 当前未发现 open PR。")

    lines.extend(["", "## 阻塞/风险", "", *risk_lines, "", "## 下一小时建议", ""])
    lines.extend(
        [
            "- 新开发任务按 feature branch + PR 推进，并在 PR 中写明测试、风险、协议/网络/安全影响。",
            "- SpellKard 改动优先用 Linux Godot headless 跑对应 smoke/check 脚本。",
            "- 服务器无显卡导致的纯 Godot 渲染器失败可标记为 ignored/blocked；GDScript 编译、类型和脚本合同失败仍必须修复。",
            "- Gensoulkyo 与 PhK-BattleServer 优先补 Dockerfile/docker-compose 回归入口，再跑服务端回归。",
            "- watchdog 发现 PR 后必须读取 PR diff 和 docs/dev 路线，满足检查才审批；发现回归代码问题必须开独立 bugfix agent/branch/PR。",
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
    merged_main_notes: list[str] = []
    for repo_name, raw_repo in sorted(repos.items()):
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        status = str(repo.get("status", ""))
        commits = repo.get("commits_last_hour") if isinstance(repo.get("commits_last_hour"), list) else []
        branch = str(repo.get("branch", ""))
        clean_baseline_branch = branch == "main" or (branch.startswith("agent/") and "...origin/main" in status)
        if clean_baseline_branch and commits and not pr_sample_failures and open_pr_count == 0:
            pr_info = pull_requests.get(repo_name) if isinstance(pull_requests.get(repo_name), dict) else {}
            raw_merged_items = pr_info.get("recent_merged_items") if isinstance(pr_info.get("recent_merged_items"), list) else []
            merged_items = [
                item
                for item in raw_merged_items
                if isinstance(item, dict) and item.get("baseRefName") == "main"
            ]
            merged_titles = [
                f"#{item.get('number')} {item.get('title')}"
                for item in merged_items[:3]
                if isinstance(item, dict)
            ]
            if merged_titles:
                merged_main_notes.append(f"- {repo_name}: 当前 {branch} 基线包含最近已合并 PR（{'; '.join(merged_titles)}），不按直接推 main 处理。")
            else:
                direct_main_risks.append(f"- {repo_name}: 当前 {branch} 近一小时有提交但未采样到最近 merged PR，需要确认是否为授权 hotfix。")

    docker_files = docker.get("repo_files") if isinstance(docker.get("repo_files"), dict) else {}
    flow_risks = list(direct_main_risks)
    if pr_sample_failures:
        flow_risks.append(f"- GitHub PR 采样失败: {', '.join(pr_sample_failures)}；流程审计不能把失败当成无 PR。")
    elif open_pr_count == 0 and not merged_main_notes:
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
    if merged_main_notes:
        flow_risks.extend(merged_main_notes)

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
            "- watchdog 停滞检测已改为 scope 路径 commit 指纹，避免同仓其他 scope 提交掩盖本 scope 停滞。",
            "- 停滞判定不再使用全局 manager heartbeat、全局 regression mtime 或同仓其他 scope 的 repo HEAD；started-only 日志和过期 active lock 会触发替代 worker。",
            "- fallback runner 已固定 HOME/XDG/GH_CONFIG_DIR、GitHub socks 代理和 credential helper 环境，worker 应可直接推分支、开 PR，并在失败时写入 final log。",
            "- PR 审批被定义为受控动作：读取 PR diff 和 docs/dev 路线、运行对应检查、确认无阻塞后才 `gh pr review --approve`；不自动合并。",
            "- regression 失败会按检查类型分发独立 bugfix agent/branch/PR，且同仓有 active worker 或 bugfix lock 时自动暂缓，避免互相覆盖。",
            "- 最近 main 提交会结合 GitHub merged PR 采样判断，避免把刚通过 PR 合入的提交误报为直接推 main。",
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
            "- watchdog/manager：发现 open PR 后读取 diff 和 docs/dev 路线，运行 gates，通过才审批 PR；发现回归失败后按仓库启动独立 bugfix agent，不自动合并。",
        ]
    ) + "\n"


def managed_change_describer_prompt() -> str:
    return """你是 gotouhou 持续中文摘要 agent（change-describer / Narrator）。

工作区：`/root/gotouhou`。运行模式：Codex `/goal` 持续目标模式。每轮必须从本机最新状态生成报告，不能复用上轮结论。

每轮必须读取最新 `/root/gotouhou/.agents/last-watchdog-summary.json`，并检查五个子仓库状态、branch/PR/最近 merged PR 状态、agent roster、systemd unit、locks、logs、reports 更新时间、Godot Linux、Docker 与 `docker-compose` 状态。报告输出到 `/root/gotouhou/.agents/reports/change-summary-latest.md`，同时更新本提示词文件。

摘要必须包含：更新前服务器状态、更新后服务器状态、本小时完成内容、Agent 状态、PR 状态、阻塞/风险、下一小时建议。文字用项目负责人能直接看懂的中文短句，不粘贴冗长 git 原文、diff、日志和命令输出。

必须写入风险：报告未更新、agent lock 残留或 started-only 日志、active 但无有效输出、dead lock 被清理、补救后未重采样、已退出 fallback 仍显示 started/running、非零退出未标 failed、未走 feature branch + PR、main 近一小时提交无法匹配 merged PR、PR 采样失败、watchdog 查出的代码问题未开独立 bugfix PR、bugfix PR 被分支保护阻塞、Godot Linux headless 未跑、服务端 Docker/`docker-compose` 回归缺失、watchdog/邮件异常、key alias 缺失、工作区已有未提交改动但被误报为完成。

不得把全局 manager heartbeat、全局 regression 文件 mtime、同仓其他 scope 的 repo HEAD 变化当成某个 scope 的推进。服务器无显卡导致的纯 Godot 渲染器失败可以写为 ignored/blocked，不算功能失败；GDScript parse/compile/type error、脚本加载失败和 UI/弹幕合同失败仍必须写为真实阻塞。

不得泄露 SMTP 密码、token、私钥、API key 或任何凭据；可以写 key alias 和 agent scope，不能写 key value。只允许写 `.agents/reports/change-summary-latest.md` 和 `.agents/agent-prompts/change-describer.md`，不修改五个子仓库，不提交，不推送。写报告和提示词必须原子更新：先写同目录临时文件，再 rename 替换；禁止先删除或清空现有报告。
"""


def managed_plan_auditor_prompt() -> str:
    return """你是 gotouhou 持续方向审计 agent（plan-auditor / Auditor）。

工作区：`/root/gotouhou`。运行模式：Codex `/goal` 持续目标模式。

每轮读取 `/root/gotouhou/docs/dev/progress.md` 与 `/root/gotouhou/docs/dev/gotouhou/**/*.md`，再检查五个子仓库状态、branch/PR/最近 merged PR 形态、最近提交、systemd/lock/log 真实进程状态、最新 watchdog summary、Godot Linux headless 能力、Docker/`docker-compose` 回归能力和 open PR。判断新增功能与开发流程是否符合 Phase 2/3/6/8、网络安全、Nakama、大厅/房间、C++ BattleServer、Godot UI/弹幕路线。

必须审计：是否缺阶段性 commit、是否直接推 main、main 近一小时提交是否能匹配 recently merged PR、是否缺 PR、PR 是否读完代码和路线后再审批、watchdog 查出的代码问题是否开独立 bugfix 分支/PR 并测试合回、SpellKard 是否用 Linux Godot headless 验证、服务端是否使用 Docker/`docker-compose` 或记录缺口、邮件内容是否及时反映 agent 真实进程状态和阻塞风险。补救动作后没有重采样、started-only 日志、active 但无有效输出、dead lock、已退出 fallback 仍显示 started、非零退出未标 failed、报告未更新、用同仓其他 scope 的 repo HEAD、全局 manager heartbeat 或全局 regression mtime 掩盖 scope 停滞，都算 agent 未正常执行，不得当成正常运行。服务器无显卡导致的纯 Godot 渲染器失败可以忽略为环境 blocked；GDScript parse/compile/type error、脚本加载失败和 UI/弹幕合同失败不能忽略。

输出 `/root/gotouhou/.agents/reports/plan-audit-latest.md`，同时更新本提示词文件。只允许写 `.agents` 下指定文件，不修改 git 仓库，不提交，不推送。不得泄露凭据。结论必须明确“符合/偏离/建议调整”，并给出可直接交给后续 worker 的中文提示词。写报告和提示词必须原子更新：先写同目录临时文件，再 rename 替换；禁止先删除或清空现有报告。
"""


def write_managed_reports(root: Path, summary: dict[str, Any]) -> None:
    reports_dir = root / ".agents" / "reports"
    prompts_dir = root / ".agents" / "agent-prompts"
    reports_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    atomic_write_text(reports_dir / "change-summary-latest.md", build_builtin_change_summary(summary))
    atomic_write_text(reports_dir / "plan-audit-latest.md", build_builtin_plan_audit(summary))
    atomic_write_text(prompts_dir / "change-describer.md", managed_change_describer_prompt())
    atomic_write_text(prompts_dir / "plan-auditor.md", managed_plan_auditor_prompt())


def lock_path(root: Path, scope_id: str) -> Path:
    return root / ".agents" / "locks" / f"{scope_id}.lock.json"


def lock_status(path: Path, now: dt.datetime, stale_minutes: int = 240) -> dict[str, Any]:
    payload = read_json(path, {})
    pid = payload.get("pid") if isinstance(payload, dict) else None
    unit = payload.get("unit") if isinstance(payload, dict) else None
    launcher = payload.get("launcher") if isinstance(payload, dict) else None
    started = parse_iso(payload.get("started_at") if isinstance(payload, dict) else None)
    unit_info = systemd_unit_info(unit if isinstance(unit, str) else None)
    stored_pid_alive = pid_alive(pid if isinstance(pid, int) else None)
    unit_active = bool(unit_info.get("active"))
    unit_main_pid_alive = bool(unit_info.get("main_pid_alive"))
    if launcher == "systemd-run" or unit:
        if isinstance(pid, int) and pid > 1:
            alive = unit_active and (stored_pid_alive or unit_main_pid_alive)
        else:
            alive = unit_active and (unit_main_pid_alive or unit_info.get("main_pid") is None)
        active_source = "systemd-unit" if alive else "systemd-unit-inactive"
    else:
        alive = stored_pid_alive
        active_source = "stored-pid" if alive else "stored-pid-dead"
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
        "launcher": launcher,
        "stored_pid_alive": stored_pid_alive,
        "unit_info": unit_info,
        "unit_active": unit_active,
        "unit_main_pid_alive": unit_main_pid_alive,
        "alive": alive,
        "active_source": active_source,
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


def cleanup_finished_lock(path: Path, status: dict[str, Any], dry_run: bool) -> dict[str, Any] | None:
    if not status.get("exists") or status.get("alive"):
        return None
    log = status.get("log") if isinstance(status.get("log"), dict) else {}
    if not log.get("exited"):
        return None
    exit_status = log.get("exit_status")
    action = {
        "type": "cleanup-finished-lock" if exit_status == 0 else "cleanup-failed-lock",
        "reason": "fallback finished cleanly" if exit_status == 0 else f"fallback exited with status {exit_status}",
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


def stop_stalled_lock(path: Path, status: dict[str, Any], reason: str, dry_run: bool) -> dict[str, Any]:
    action = {
        "type": "stop-stalled-agent",
        "reason": reason,
        "lock": str(path),
        "lock_status": status,
        "dry_run": dry_run,
    }
    unit = status.get("unit")
    pid = status.get("pid")
    if dry_run:
        return action
    if isinstance(unit, str) and unit:
        code, output = run_command(["systemctl", "stop", unit], Path("/"), timeout=20)
        action["systemctl_stop"] = {"status": code, "output": output[-1000:]}
    elif isinstance(pid, int) and pid > 1:
        try:
            os.kill(pid, 15)
            action["pid_signal"] = "SIGTERM"
        except OSError as exc:
            action["pid_signal_error"] = str(exc)
    refreshed = lock_status(path, utcnow())
    action["post_stop_lock"] = refreshed
    if not refreshed.get("alive"):
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
- Use the inherited GitHub CLI auth and proxy from the fallback runner. If `git push` or `gh pr create` fails, write the exact non-secret blocker to your final status; do not remain running after a local commit with no PR.
- If watchdog/regression reveals a code failure in your scope, switch to a dedicated `fix/<area>` branch/PR first; after tests pass, request merge and report any branch protection blocker.
- Write a concise final status to `/root/gotouhou/.agents/logs/{scope_id}-final.md`.
"""


def summary_agent_prompt(reason: str, key_assignment: dict[str, Any]) -> str:
    return f"""{goal_prompt_preamble("change-describer", reason, key_assignment)}

你是 gotouhou 持续中文摘要 agent（change-describer / Narrator）。

工作区：/root/gotouhou
运行模式：Codex `/goal` 持续目标模式。每小时被 watchdog 拉起时，都要完成一次独立摘要并写回状态；异常中断后从 `.agents` 最新状态恢复。

任务：
1. 先读取最新 `/root/gotouhou/.agents/last-watchdog-summary.json`，再检查五个子仓库当前状态、最近一小时提交、branch/PR 状态、`/root/gotouhou/.agents/agent-roster.json`、systemd unit、locks、logs 和 reports 更新时间。
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
- 如果发现 watchdog 误启动、重复启动、lock 残留、报告未更新、key 分配缺失、已退出 fallback 仍显示 started/running、非零退出未标 failed、未走分支/PR、watchdog 查出的代码问题未开独立 bugfix PR、Godot/Docker 检查缺失，必须写入风险。
- 只允许写 `.agents/reports/change-summary-latest.md` 和 `.agents/agent-prompts/change-describer.md`；不要改五个子仓库里的文件。
"""


def audit_agent_prompt(reason: str, key_assignment: dict[str, Any]) -> str:
    return f"""{goal_prompt_preamble("plan-auditor", reason, key_assignment)}

你是 gotouhou 持续方向审计 agent（plan-auditor / Auditor）。

工作区：/root/gotouhou
运行模式：Codex `/goal` 持续目标模式。每小时被 watchdog 拉起时，都要完成一次方向审计并给出后续 agent 提示词；异常中断后从 `.agents` 最新状态恢复。

任务：
1. 阅读 `/root/gotouhou/docs/dev/progress.md` 和 `/root/gotouhou/docs/dev/gotouhou/**/*.md` 中当前阶段计划，重点关注 Phase 2/3/6/8、网络安全、Nakama、大厅、C++ BattleServer、Godot UI/弹幕。
2. 检查五个子仓库 `docs`、`Gensoulkyo`、`SpellKard`、`PhK-Protocol`、`PhK-BattleServer` 的当前状态、branch/PR 形态、最近提交、systemd/lock/log 真实进程状态和最新 watchdog summary，判断新增功能是否符合计划方向。
3. 检查开发流程是否偏离：是否缺少阶段性 commit、是否直接推 main、是否缺 PR、watchdog 查出的代码问题是否开独立 bugfix branch/PR 并测试合回、是否缺 Godot Linux headless 或 Docker/`docker-compose` 回归。
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
Treat `codex exec` fallback workers as per-round executors: after
`[watchdog] exited status=0` and an inactive systemd unit, the scope is completed
for that round, not still running. Non-zero exits are failures that need a
replacement worker or a scoped bugfix.
Ensure the four development scopes are covered:
- spellkard-bullet
- spellkard-ui
- gensoulkyo-lobby
- phk-battle-server

If a scope is missing, blocked, or stale, launch a scoped worker or continue the
work directly without reverting unrelated edits. Keep `/root/gotouhou/.agents`
updated. Use branch + PR flow for repository changes; do not directly push main
except for explicit emergency hotfixes authorized by the manager.
If a worker has a local commit but push/PR failed, treat it as publish-blocked,
not running: stop stale units, clear the scope lock, publish with available
manager credentials, and record the action in the next watchdog/mail snapshot.

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


def bugfix_prompt(
    scope_id: str,
    reason: str,
    key_assignment: dict[str, Any],
    failures: list[dict[str, Any]],
    route: dict[str, Any],
) -> str:
    failure_lines = "\n".join(
        f"- {item.get('name')} status={item.get('status')} blocked={item.get('blocked', False)} cwd={item.get('cwd', '')} tail={str(item.get('output_tail', ''))[:300]}"
        for item in failures
    )
    repo = str(route.get("repo", "SpellKard"))
    branch = str(route.get("branch", "fix/watchdog-regression"))
    kind = str(route.get("kind", "generic"))
    cwd = "/root/gotouhou" if repo == "docs" and kind == "protocol" else f"/root/gotouhou/{repo}"
    route_docs = "\n".join(f"- `/root/gotouhou/docs/{path}`" for path in docs_route_paths_for_repo(repo if repo != "docs" else "PhK-Protocol"))
    if kind == "spellkard-godot":
        check_text = "使用 `/root/gotouhou/Godot_v4.7-stable_linux.x86_64` 从 `/root/gotouhou/SpellKard/godot` 运行相关 headless 脚本；纯 renderer/RenderingDevice 问题可标记为环境 blocked，GDScript/合同失败必须修复。"
    elif kind == "server":
        check_text = "优先使用 `docker-compose` 运行服务端回归；涉及协议/网络/安全时必须运行 `/root/gotouhou/docs/ops/protocol_audit_check.py`。"
    elif kind == "protocol":
        check_text = "先运行 `/root/gotouhou/docs/ops/protocol_audit_check.py` 定位失败仓库，再在实际失败仓库从最新 `origin/main` 创建 `fix/<area>` 分支；涉及服务端时同时使用 `docker-compose` 回归。"
    else:
        check_text = "运行失败项对应的最小回归，并把仍阻塞的环境原因写入 PR。"
    return f"""{goal_prompt_preamble(scope_id, reason, key_assignment)}

你是 gotouhou watchdog 代码回归修复 agent。

工作区：`{cwd}`
建议分支：从最新 `origin/main` 创建或继续 `{branch}`
目标：修复 watchdog 回归检查查出的代码问题。不得把纯环境缺口伪装成功能修复；若是服务器无显卡导致的纯 Godot renderer/RenderingDevice 失败，可标记为环境 blocked，但 GDScript parse/compile/type error、脚本加载失败、UI/弹幕合同失败必须修复。

当前失败：
{failure_lines or "- 未提供失败明细，请读取 /root/gotouhou/.agents/checks/latest-regression.json。"}

必须执行：
- 先读最新 regression JSON 和以下 docs/dev 路线：
{route_docs}
- 只修改与回归失败直接相关的最小文件集，不回滚他人或其他 agent 改动。
- {check_text}
- 使用 UTF-8 和 Linux LF。
- 阶段性 commit，推送 bugfix 分支，创建 PR；PR 正文写明测试结果、忽略的纯环境问题、协议/网络/安全影响和未解决风险。
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
    cleanup_finished_lock(lock, current_lock, dry_run=dry_run)
    current_lock = lock_status(lock, now)
    cleanup_dead_lock(lock, current_lock, dry_run=dry_run)
    current_lock = lock_status(lock, now)
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
            shell_export_line("HOME", "/root"),
            shell_export_line("XDG_CONFIG_HOME", "/root/.config"),
            shell_export_line("GH_CONFIG_DIR", "/root/.config/gh"),
            shell_export_line("GOCACHE", "/root/.cache/go-build"),
            shell_export_line("GOPATH", "/root/go"),
            shell_export_line("HTTPS_PROXY", DEFAULT_GH_PROXY),
            shell_export_line("HTTP_PROXY", DEFAULT_GH_PROXY),
            shell_export_line("ALL_PROXY", DEFAULT_GH_PROXY),
            shell_export_line("https_proxy", DEFAULT_GH_PROXY),
            shell_export_line("http_proxy", DEFAULT_GH_PROXY),
            shell_export_line("all_proxy", DEFAULT_GH_PROXY),
            "git config --global credential.https://github.com.helper '!/usr/bin/gh auth git-credential' >/dev/null 2>&1 || true",
            "/usr/bin/gh auth setup-git >/dev/null 2>&1 || true",
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
    risk_previous: dict[str, Any] | None,
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
    head_state = scoped_head_fingerprint(root, scope)
    current_head = str(head_state.get("head", ""))
    current_head_fingerprint = str(head_state.get("fingerprint", ""))
    repo_head = str(head_state.get("repo_head", ""))
    latest_log = latest_log_path(root, scope_id)
    log = log_status(latest_log)
    runtime_log, runtime_log_path = runtime_log_for_roster(roster_entry, latest_log)
    log_mtime = latest_log.stat().st_mtime if latest_log and latest_log.exists() else None
    heartbeat_mtime = scope_heartbeat_mtime(root, scope_id)
    test_signal = scope_test_signal(root, scope_id, repo)
    previous_scope = ((previous or {}).get("scopes") or {}).get(scope_id, {})
    risk_previous_scope = ((risk_previous or {}).get("scopes") or {}).get(scope_id, {})

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
    has_active_repo_lock, active_repo_lock_reason = repo_has_active_scope_lock(root, repo, scope_id, now)
    if has_active_repo_lock:
        deferred = True
        deferred_reason = active_repo_lock_reason
        actions.append({"type": "scope-deferred", "scope": scope_id, "repo": repo, "reason": active_repo_lock_reason})
    lock_file = lock_path(root, scope_id)
    lock = lock_status(lock_file, now)
    finished_cleanup_action = cleanup_finished_lock(lock_file, lock, dry_run=dry_run)
    if finished_cleanup_action:
        actions.append(finished_cleanup_action)
        lock = lock_status(lock_file, now)
    cleanup_action = cleanup_dead_lock(lock_file, lock, dry_run=dry_run)
    if cleanup_action:
        actions.append(cleanup_action)
        lock = lock_status(lock_file, now)
        roster_entry["status"] = "failed"
        roster_entry["last_failure_reason"] = cleanup_action.get("reason")
    reconcile_roster_exit_status(roster_entry, current_head=current_head, lock=lock, runtime_log=runtime_log, now=now)

    observed_log = lock.get("log") if lock.get("alive") and isinstance(lock.get("log"), dict) and lock["log"].get("exists") else log
    previous_log_hash = previous_scope.get("log_useful_hash")
    previous_fingerprint = previous_scope.get("head_fingerprint") or previous_scope.get("head")
    commit_progress = scoped_commit_progress(previous, previous_scope, current_head, current_head_fingerprint)
    diff_progress = bool(previous is None or diff_hash != previous_scope.get("diff_hash"))
    log_progress = bool(observed_log.get("useful_hash") and observed_log.get("useful_hash") != previous_log_hash)
    heartbeat_progress = bool(heartbeat_mtime is not None and heartbeat_mtime != previous_scope.get("heartbeat_mtime"))
    test_log_progress = bool(test_signal and test_signal != previous_scope.get("test_signal"))
    progress = bool(commit_progress or diff_progress or log_progress or heartbeat_progress or test_log_progress)
    scope_report_path = report_path(root, scope_id)
    report_expected = scope_report_path is not None
    report_updated = False
    if scope_report_path and scope_report_path.exists():
        report_mtime = scope_report_path.stat().st_mtime
        if report_mtime != previous_scope.get("report_mtime"):
            progress = True
            report_updated = True
    else:
        report_mtime = None
    recent_launch_failed = bool(lock.get("dead_unfinished") or log_finished_with_failure(runtime_log))
    fallback_log_path = roster_entry.get("fallback_log_path") if isinstance(roster_entry.get("fallback_log_path"), str) else ""
    if fallback_log_path and latest_log and Path(fallback_log_path) == latest_log and not lock.get("alive") and not log.get("exited"):
        recent_launch_failed = True
    if recent_launch_failed:
        progress = False

    previous_stalled_count = max(
        int(previous_scope.get("stalled_count", 0) or 0),
        int(risk_previous_scope.get("stalled_count", 0) or 0),
    )
    stalled_count = previous_stalled_count if progress and same_hour else (0 if progress else previous_stalled_count + 1)

    active_stall_reason = active_lock_stall_reason(lock, observed_log, progress)
    if active_stall_reason:
        recent_launch_failed = True

    active_stalled = bool(lock.get("alive") and (active_stall_reason or (not progress and stalled_count >= stalled_samples)))
    action_reason = ""
    should_start = False
    completed = roster_entry.get("status") == "completed"
    continuous = bool(scope.get("continuous"))
    last_started = parse_iso(roster_entry.get("last_started_at") if isinstance(roster_entry.get("last_started_at"), str) else None)
    started_this_hour = bool(last_started and hour_bucket(last_started) == hour_bucket(now))
    due_for_continuation = bool(continuous and not lock.get("alive") and not started_this_hour)
    if deferred:
        should_start = False
    elif active_stalled:
        action_reason = active_stall_reason or f"active agent stalled for {stalled_count} samples"
        stop_action = stop_stalled_lock(lock_file, lock, action_reason, dry_run=dry_run)
        actions.append(stop_action)
        lock = lock_status(lock_file, now)
        if not lock.get("alive"):
            should_start = True
            roster_entry["status"] = "failed"
            roster_entry["last_failure_reason"] = action_reason
        else:
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
            action_reason = "scheduled hourly continuous /goal scope"
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
            started_this_hour = True
            due_for_continuation = False

    return {
        "scope": scope_id,
        "repo": repo,
        "nickname": roster_entry.get("nickname", scope.get("nickname")),
        "status": roster_entry.get("status", "unknown"),
        "record_exists": record_exists,
        "head": current_head,
        "repo_head": repo_head,
        "head_commit": head_state.get("commit"),
        "head_fingerprint": current_head_fingerprint,
        "head_source": head_state.get("source"),
        "diff_hash": diff_hash,
        "scoped_dirty": scoped_text.splitlines()[:20],
        "log_mtime": log_mtime,
        "log_useful_hash": observed_log.get("useful_hash"),
        "log": observed_log,
        "latest_log": log,
        "runtime_log_path": str(runtime_log_path) if runtime_log_path else None,
        "runtime_log": runtime_log,
        "heartbeat_mtime": heartbeat_mtime,
        "test_signal": test_signal,
        "report_mtime": report_mtime,
        "report_expected": report_expected,
        "report_updated": report_updated,
        "last_seen_at": roster_entry.get("last_seen_at"),
        "last_started_at": roster_entry.get("last_started_at"),
        "last_start_reason": roster_entry.get("last_start_reason"),
        "progress": progress,
        "progress_signals": {
            "commit": commit_progress,
            "scoped_diff": diff_progress,
            "heartbeat": heartbeat_progress,
            "test_log": test_log_progress,
            "useful_log": log_progress,
            "report": report_updated,
        },
        "stall_signals": {
            "no_commit": not commit_progress,
            "no_scoped_diff": not diff_progress,
            "no_heartbeat": not heartbeat_progress,
            "no_test_log": not test_log_progress,
            "no_useful_log": not log_has_useful_output(observed_log),
            "report_not_updated": report_expected and not report_updated,
            "active_stall_reason": active_stall_reason,
        },
        "recent_launch_failed": recent_launch_failed,
        "deferred": deferred,
        "deferred_reason": deferred_reason,
        "stalled_count": stalled_count,
        "lock": lock,
        "fallback_log_path": roster_entry.get("fallback_log_path"),
        "key_alias": key_assignment.get("alias"),
        "key_available": key_assignment.get("available"),
        "continuous": continuous,
        "started_this_hour": started_this_hour,
        "due_for_continuation": due_for_continuation and not deferred,
        "actions": actions,
    }


def refresh_scope_runtime(
    *,
    root: Path,
    scope_id: str,
    scope: dict[str, Any],
    scope_state: dict[str, Any],
    previous: dict[str, Any] | None,
    risk_previous: dict[str, Any] | None,
    now: dt.datetime,
    same_hour: bool,
) -> dict[str, Any]:
    repo = str(scope["repo"])
    scoped_text, diff_hash = scoped_status(root, scope)
    head_state = scoped_head_fingerprint(root, scope)
    current_head = str(head_state.get("head", ""))
    current_head_fingerprint = str(head_state.get("fingerprint", ""))
    repo_head = str(head_state.get("repo_head", ""))
    latest_log = latest_log_path(root, scope_id)
    log = log_status(latest_log)
    fallback_log_path = scope_state.get("fallback_log_path") if isinstance(scope_state.get("fallback_log_path"), str) else ""
    runtime_log_path = Path(fallback_log_path) if fallback_log_path else latest_log
    runtime_log = log_status(runtime_log_path)
    log_mtime = latest_log.stat().st_mtime if latest_log and latest_log.exists() else None
    heartbeat_mtime = scope_heartbeat_mtime(root, scope_id)
    test_signal = scope_test_signal(root, scope_id, repo)
    previous_scope = ((previous or {}).get("scopes") or {}).get(scope_id, {})
    risk_previous_scope = ((risk_previous or {}).get("scopes") or {}).get(scope_id, {})
    previous_log_hash = previous_scope.get("log_useful_hash")
    lock = lock_status(lock_path(root, scope_id), now)
    observed_log = lock.get("log") if lock.get("alive") and isinstance(lock.get("log"), dict) and lock["log"].get("exists") else log

    previous_fingerprint = previous_scope.get("head_fingerprint") or previous_scope.get("head")
    commit_progress = scoped_commit_progress(previous, previous_scope, current_head, current_head_fingerprint)
    diff_progress = bool(previous is None or diff_hash != previous_scope.get("diff_hash"))
    log_progress = bool(observed_log.get("useful_hash") and observed_log.get("useful_hash") != previous_log_hash)
    heartbeat_progress = bool(heartbeat_mtime is not None and heartbeat_mtime != previous_scope.get("heartbeat_mtime"))
    test_log_progress = bool(test_signal and test_signal != previous_scope.get("test_signal"))
    progress = bool(commit_progress or diff_progress or log_progress or heartbeat_progress or test_log_progress)
    scope_report_path = report_path(root, scope_id)
    report_expected = scope_report_path is not None
    report_updated = False
    if scope_report_path and scope_report_path.exists():
        report_mtime = scope_report_path.stat().st_mtime
        if report_mtime != previous_scope.get("report_mtime"):
            progress = True
            report_updated = True
    else:
        report_mtime = None

    previous_stalled_count = max(
        int(previous_scope.get("stalled_count", scope_state.get("stalled_count", 0)) or 0),
        int(risk_previous_scope.get("stalled_count", 0) or 0),
        int(scope_state.get("stalled_count", 0) or 0),
    )
    stalled_count = previous_stalled_count if progress and same_hour else (0 if progress else previous_stalled_count + 1)

    recent_launch_failed = bool(lock.get("dead_unfinished") or log_finished_with_failure(runtime_log))
    active_stall_reason = active_lock_stall_reason(lock, observed_log, progress)
    if active_stall_reason:
        recent_launch_failed = True

    status = scope_state.get("status", "unknown")
    if not lock.get("alive") and runtime_log.get("exited") and status in {"started", "running", "active"}:
        status = "completed" if runtime_log.get("exit_status") == 0 else "failed"
    last_started = parse_iso(scope_state.get("last_started_at") if isinstance(scope_state.get("last_started_at"), str) else None)
    started_this_hour = bool(last_started and hour_bucket(last_started) == hour_bucket(now))
    continuous = bool(scope.get("continuous"))

    refreshed = dict(scope_state)
    refreshed.update(
        {
            "head": current_head,
            "repo_head": repo_head,
            "head_commit": head_state.get("commit"),
            "head_fingerprint": current_head_fingerprint,
            "head_source": head_state.get("source"),
            "diff_hash": diff_hash,
            "scoped_dirty": scoped_text.splitlines()[:20],
            "log_mtime": log_mtime,
            "log_useful_hash": observed_log.get("useful_hash"),
            "log": observed_log,
            "latest_log": log,
            "runtime_log_path": str(runtime_log_path) if runtime_log_path else None,
            "runtime_log": runtime_log,
            "heartbeat_mtime": heartbeat_mtime,
            "test_signal": test_signal,
            "report_mtime": report_mtime,
            "report_expected": report_expected,
            "report_updated": report_updated,
            "progress": progress,
            "progress_signals": {
                "commit": commit_progress,
                "scoped_diff": diff_progress,
                "heartbeat": heartbeat_progress,
                "test_log": test_log_progress,
                "useful_log": log_progress,
                "report": report_updated,
            },
            "stall_signals": {
                "no_commit": not commit_progress,
                "no_scoped_diff": not diff_progress,
                "no_heartbeat": not heartbeat_progress,
                "no_test_log": not test_log_progress,
                "no_useful_log": not log_has_useful_output(observed_log),
                "report_not_updated": report_expected and not report_updated,
                "active_stall_reason": active_stall_reason,
            },
            "recent_launch_failed": recent_launch_failed,
            "stalled_count": stalled_count,
            "lock": lock,
            "status": status,
            "continuous": continuous,
            "started_this_hour": started_this_hour,
            "due_for_continuation": bool(continuous and not lock.get("alive") and not started_this_hour),
            "resampled_at": iso(now),
        }
    )
    return refreshed


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


def regression_failure_route(failure: dict[str, Any]) -> dict[str, Any] | None:
    name = str(failure.get("name", ""))
    route = BUGFIX_FAILURE_ROUTES.get(name)
    if route is None:
        return None
    if failure.get("blocked") or failure.get("ignored"):
        return None
    return route


def grouped_regression_failures(failed: list[Any]) -> dict[str, dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for raw_failure in failed:
        failure = raw_failure if isinstance(raw_failure, dict) else {}
        route = regression_failure_route(failure)
        if route is None:
            continue
        scope_id = str(route["scope"])
        group = groups.setdefault(scope_id, {"route": route, "failures": []})
        group["failures"].append(failure)
    return groups


def repo_has_active_bugfix_or_worker(root: Path, repo_name: str, scope_id: str, now: dt.datetime) -> tuple[bool, str]:
    for other_scope_id in scope_ids_for_repo(repo_name):
        status = lock_status(lock_path(root, other_scope_id), now)
        if status.get("alive"):
            return True, f"{repo_name} has active worker lock {other_scope_id}; defer bugfix {scope_id}"
    for lock in sorted((root / ".agents" / "locks").glob(f"{BUGFIX_SCOPE_PREFIX}*.lock.json")):
        status = lock_status(lock, now)
        if not status.get("alive"):
            continue
        payload = read_json(lock, {})
        if isinstance(payload, dict) and payload.get("scope") != scope_id:
            cwd = str(payload.get("cwd", ""))
            if cwd == str(root / repo_name) or cwd == str(root):
                return True, f"{repo_name} has active bugfix lock {payload.get('scope')}; defer bugfix {scope_id}"
    return False, ""


def maybe_start_regression_bugfixes(
    *,
    root: Path,
    regression: dict[str, Any],
    pull_requests: dict[str, Any],
    codex_bin: str,
    key_assignments: dict[str, dict[str, Any]],
    keyring: dict[str, Any],
    dry_run: bool,
) -> list[dict[str, Any]]:
    failed = regression.get("failed") if isinstance(regression.get("failed"), list) else []
    actions: list[dict[str, Any]] = []
    for scope_id, group in sorted(grouped_regression_failures(failed).items()):
        route = group["route"]
        failures = group["failures"]
        repo_name = str(route["repo"])
        branch = str(route["branch"])
        existing_pr = open_pr_for_branch(pull_requests, repo_name, branch)
        if existing_pr:
            actions.append(
                {
                    "type": "bugfix-pr-open",
                    "repo": repo_name,
                    "scope": scope_id,
                    "branch": branch,
                    "reason": f"{repo_name} regression has open bugfix PR",
                    "url": existing_pr.get("url"),
                    "number": existing_pr.get("number"),
                    "mergeStateStatus": existing_pr.get("mergeStateStatus"),
                    "failures": failures,
                }
            )
            continue
        active, defer_reason = repo_has_active_bugfix_or_worker(root, repo_name, scope_id, utcnow())
        if active:
            actions.append(
                {
                    "type": "bugfix-deferred",
                    "repo": repo_name,
                    "scope": scope_id,
                    "branch": branch,
                    "reason": defer_reason,
                    "failures": failures,
                }
            )
            continue
        key_assignment = key_assignments.get(scope_id, select_key_alias(scope_id, keyring))
        reason = f"watchdog found {repo_name} regression checks failing"
        cwd = root if repo_name == "docs" and route.get("kind") == "protocol" else root / repo_name
        actions.append(
            {
                "type": "start-bugfix-agent",
                "scope": scope_id,
                "repo": repo_name,
                "branch": branch,
                "reason": reason,
                "failures": failures,
                "result": start_background_codex(
                    root=root,
                    scope_id=scope_id,
                    prompt=bugfix_prompt(scope_id, reason, key_assignment, failures, route),
                    cwd=cwd,
                    codex_bin=codex_bin,
                    key_assignment=key_assignment,
                    key_value=selected_key_value(key_assignment, keyring),
                    dry_run=dry_run,
                ),
            }
        )
    return actions


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
    for scope_id in sorted({str(route["scope"]) for route in BUGFIX_FAILURE_ROUTES.values()}):
        key_assignments[scope_id] = select_key_alias(scope_id, keyring)
    latest_snapshot = load_previous_snapshot(snapshot_dir)
    previous = load_previous_distinct_snapshot(snapshot_dir, current_bucket) or latest_snapshot
    risk_previous = latest_snapshot
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
            risk_previous=risk_previous,
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
    bugfix_actions = maybe_start_regression_bugfixes(
        root=root,
        regression=regression,
        pull_requests=pull_requests,
        codex_bin=args.codex_bin,
        key_assignments=key_assignments,
        keyring=keyring,
        dry_run=args.dry_run,
    )
    actions.extend(bugfix_actions)

    actions.extend(maybe_approve_pull_requests(root, pull_requests, args.approve_prs))
    actions.extend(stale_artifact_actions(root, now))
    initial_scopes = scopes
    initial_repos = repos
    initial_manager = manager
    initial_systemd_mail = systemd_mail
    initial_runtime = runtime
    initial_reports = reports
    resampled_after_actions = bool(actions)
    if resampled_after_actions:
        resample_now = utcnow()
        repos = {name: collect_repo(root, name, resample_now) for name in DEFAULT_REPOS}
        manager = collect_manager(root, resample_now, args.manager_stale_minutes)
        systemd_mail = collect_systemd_mail(resample_now)
        runtime = collect_runtime_environment(root, resample_now, Path(args.godot_bin).resolve())
        reports = collect_reports(root)
        scopes = {
            scope_id: refresh_scope_runtime(
                root=root,
                scope_id=scope_id,
                scope=scope,
                scope_state=initial_scopes[scope_id],
                previous=previous,
                risk_previous=risk_previous,
                now=resample_now,
                same_hour=same_hour,
            )
            for scope_id, scope in DEFAULT_SCOPES.items()
        }
    final_generated_at = iso(utcnow())
    summary = {
        "version": 1,
        "generated_at": final_generated_at,
        "hour_bucket": current_bucket,
        "root": str(root),
        "dry_run": bool(args.dry_run),
        "resampled_after_actions": resampled_after_actions,
        "manager": manager,
        "initial_manager": initial_manager,
        "keyring": keyring_public_summary(keyring),
        "key_assignments": key_assignments,
        "systemd_mail": systemd_mail,
        "initial_systemd_mail": initial_systemd_mail,
        "runtime": runtime,
        "initial_runtime": initial_runtime,
        "pull_requests": pull_requests,
        "reports": reports,
        "initial_reports": initial_reports,
        "regression": regression,
        "repos": repos,
        "initial_repos": initial_repos,
        "scopes": scopes,
        "initial_scopes": initial_scopes,
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
        report_sample_now = utcnow()
        summary["scopes"] = {
            scope_id: refresh_scope_runtime(
                root=root,
                scope_id=scope_id,
                scope=scope,
                scope_state=summary["scopes"][scope_id],
                previous=previous,
                risk_previous=risk_previous,
                now=report_sample_now,
                same_hour=same_hour,
            )
            for scope_id, scope in DEFAULT_SCOPES.items()
        }
        summary["generated_at"] = iso(report_sample_now)
        summary["report_resampled_at"] = iso(report_sample_now)
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
