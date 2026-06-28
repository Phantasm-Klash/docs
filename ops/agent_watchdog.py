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
UTC = dt.timezone.utc


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


def run_command(command: list[str], cwd: Path, timeout: int = 20) -> tuple[int, str]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 127, str(exc)
    return completed.returncode, completed.stdout.strip()


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


def scoped_status(root: Path, scope: dict[str, Any]) -> tuple[str, str]:
    repo = root / str(scope["repo"])
    paths = [str(path) for path in scope.get("paths", ())]
    status = run_git(repo, ["status", "--short", "--", *paths])
    diffstat = run_git(repo, ["diff", "--stat", "--", *paths])
    text = "\n".join([status, diffstat]).strip()
    return text, sha256_text(text)


def collect_manager(root: Path, now: dt.datetime, stale_minutes: int) -> dict[str, Any]:
    agents_dir = root / ".agents"
    status_path = agents_dir / "manager-status.md"
    heartbeat_path = agents_dir / "manager-heartbeat.json"
    heartbeat = read_json(heartbeat_path, {})

    status_mtime = newest_file_mtime([status_path, heartbeat_path])
    age_seconds = None
    if status_mtime is not None:
        age_seconds = max(0, int(now.timestamp() - status_mtime))

    mode = "unknown"
    if status_path.exists():
        text = status_path.read_text(encoding="utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("Mode:"):
                mode = line.split(":", 1)[1].strip()
                break

    return {
        "mode": mode,
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


def write_manager_files(root: Path, summary: dict[str, Any], now: dt.datetime) -> None:
    agents_dir = root / ".agents"
    heartbeat_path = agents_dir / "manager-heartbeat.json"
    status_path = agents_dir / "manager-status.md"
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    repos = summary.get("repos") if isinstance(summary.get("repos"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []

    heartbeat = {
        "updated_at": iso(now),
        "mode": "goal-active",
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
        "Mode: goal-active",
        "Goal: sustained multi-repository development for bullet engine, frontend/assets, Nakama lobby, and C++ battle server.",
        "Manager workspace: /root/gotouhou",
        "Git topology: root .git is invalid/empty; child repositories are the commit roots.",
        "Encoding policy: UTF-8, Linux LF.",
        "",
        "## Active goal scopes",
        "",
        "| Scope | Repo | Status | Progress | Stalled | Head | Actions |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for scope_id, raw_scope in sorted(scopes.items()):
        scope = raw_scope if isinstance(raw_scope, dict) else {}
        lines.append(
            "| "
            f"{scope_id} | {scope.get('repo', '')} | {scope.get('status', '')} | "
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
            "- Scope stagnation uses the conservative two-sample rule.",
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
    return {"version": 1, "created_at": iso(now), "scopes": scopes, "manager": {"status": "goal-active"}}


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


def lock_path(root: Path, scope_id: str) -> Path:
    return root / ".agents" / "locks" / f"{scope_id}.lock.json"


def lock_status(path: Path, now: dt.datetime, stale_minutes: int = 240) -> dict[str, Any]:
    payload = read_json(path, {})
    pid = payload.get("pid") if isinstance(payload, dict) else None
    started = parse_iso(payload.get("started_at") if isinstance(payload, dict) else None)
    alive = pid_alive(pid if isinstance(pid, int) else None)
    stale = False
    if started is not None:
        stale = (now - started).total_seconds() > stale_minutes * 60
    return {
        "path": str(path),
        "exists": path.exists(),
        "pid": pid,
        "alive": alive,
        "stale": stale,
        "started_at": iso(started) if started else None,
    }


def fallback_prompt(scope_id: str, scope: dict[str, Any], reason: str) -> str:
    if scope.get("kind") == "summary":
        return summary_agent_prompt(reason)
    if scope.get("kind") == "audit":
        return audit_agent_prompt(reason)

    repo = scope["repo"]
    paths = "\n".join(f"- {path}" for path in scope.get("paths", ()))
    return f"""You are a gotouhou fallback Codex worker for scope `{scope_id}`.

Reason for launch: {reason}
Repository root: /root/gotouhou/{repo}
Workspace root: /root/gotouhou

You are not alone in the codebase. Do not revert user or other-agent edits.
Before editing, inspect `git status --short --branch` and the scoped files.
Before committing or pushing, acquire the repo git lock with:
`flock /root/gotouhou/.agents/locks/git-{repo}.lock -c '<git commands>'`.

Scope summary: {scope["summary"]}
Allowed paths:
{paths}

Implementation requirements:
- Continue the current main branch work for this scope.
- Keep changes inside the allowed paths.
- Use UTF-8 and Linux LF.
- Run the relevant local checks for the repository.
- For network/protocol/server scopes, run `/root/gotouhou/docs/ops/protocol_audit_check.py`.
- Commit and push to `main`, rebasing on `origin/main` if needed.
- Write a concise final status to `/root/gotouhou/.agents/logs/{scope_id}-final.md`.
"""


def summary_agent_prompt(reason: str) -> str:
    return f"""你是 gotouhou 持续中文摘要 agent。

启动原因：{reason}
工作区：/root/gotouhou

任务：
1. 检查五个子仓库最近一小时的提交、未提交改动、watchdog summary、agent roster 和 logs。
2. 用简单中文生成面向项目负责人的功能完成摘要，不要粘贴冗长 git/status 原文。
3. 输出 `/root/gotouhou/.agents/reports/change-summary-latest.md`。
4. 同时更新 `/root/gotouhou/.agents/agent-prompts/change-describer.md`，记录你自己的最新提示词。
5. 不修改任何 git 仓库文件，不提交，不推送。

摘要格式：
- 服务器状态：每个子仓库一句话。
- 本小时完成：按功能写 3-8 条。
- 阻塞/风险：只写需要人关注的事项。
- 下一小时建议：最多 5 条。
"""


def audit_agent_prompt(reason: str) -> str:
    return f"""你是 gotouhou 持续方向审计 agent。

启动原因：{reason}
工作区：/root/gotouhou

任务：
1. 阅读 `/root/gotouhou/docs/dev` 中的开发计划和 `/root/gotouhou/docs/dev/progress.md`。
2. 对照五个子仓库当前状态，审计新增功能是否偏离当前阶段计划。
3. 如果发现明显偏离，给出需要调整的 agent 方向和替换提示词；如果未偏离，明确说明。
4. 输出 `/root/gotouhou/.agents/reports/plan-audit-latest.md`。
5. 同时更新 `/root/gotouhou/.agents/agent-prompts/plan-auditor.md`，记录你自己的最新提示词。
6. 不修改任何 git 仓库文件，不提交，不推送。

审计格式：
- 当前阶段判断。
- 符合计划的新增功能。
- 潜在偏离或优先级问题。
- 建议调整的 agent 提示词：按 scope 给出可直接使用的中文提示词。
"""


def manager_prompt(reason: str) -> str:
    return f"""You are the gotouhou fallback manager.

Reason for launch: {reason}
Workspace root: /root/gotouhou

Inspect `/root/gotouhou/.agents/manager-status.md`, the five child repositories,
and any active worker logs under `/root/gotouhou/.agents/logs`.
Ensure the four development scopes are covered:
- spellkard-bullet
- spellkard-ui
- gensoulkyo-lobby
- phk-battle-server

If a scope is missing, blocked, or stale, launch a scoped worker or continue the
work directly without reverting unrelated edits. Keep `/root/gotouhou/.agents`
updated. Commit and push only valid repository changes.
"""


def start_background_codex(
    *,
    root: Path,
    scope_id: str,
    prompt: str,
    cwd: Path,
    codex_bin: str,
    dry_run: bool,
) -> dict[str, Any]:
    now = utcnow()
    agents_dir = root / ".agents"
    locks_dir = agents_dir / "locks"
    logs_dir = agents_dir / "logs"
    prompts_dir = agents_dir / "prompts"
    lock = lock_path(root, scope_id)
    current_lock = lock_status(lock, now)
    if current_lock["alive"]:
        return {"started": False, "reason": "lock-active", "lock": current_lock}
    if dry_run:
        return {"started": False, "reason": "dry-run", "lock": current_lock}

    locks_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    prompts_dir.mkdir(parents=True, exist_ok=True)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    prompt_path = prompts_dir / f"{scope_id}-{stamp}.txt"
    log_path = logs_dir / f"{scope_id}-{stamp}.log"
    prompt_path.write_text(prompt, encoding="utf-8", newline="\n")

    quoted_lock = shlex.quote(str(lock))
    quoted_log = shlex.quote(str(log_path))
    quoted_prompt = shlex.quote(str(prompt_path))
    quoted_codex = shlex.quote(codex_bin)
    quoted_cwd = shlex.quote(str(cwd))
    quoted_root = shlex.quote(str(root))
    script = (
        "set -u; "
        f"trap 'rm -f {quoted_lock}' EXIT; "
        f"echo '[watchdog] started {scope_id} at {iso(now)}' >> {quoted_log}; "
        f"cd {quoted_cwd}; "
        f"{quoted_codex} exec --dangerously-bypass-approvals-and-sandbox "
        f"--add-dir {quoted_root} -C {quoted_cwd} - < {quoted_prompt} >> {quoted_log} 2>&1; "
        f"status=$?; echo '[watchdog] exited status='$status >> {quoted_log}; exit $status"
    )
    try:
        process = subprocess.Popen(
            ["/bin/sh", "-c", script],
            cwd=str(cwd),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError as exc:
        return {"started": False, "reason": f"spawn-failed: {exc}", "lock": current_lock}

    write_json(
        lock,
        {
            "scope": scope_id,
            "pid": process.pid,
            "started_at": iso(now),
            "prompt_path": str(prompt_path),
            "log_path": str(log_path),
            "cwd": str(cwd),
        },
    )
    return {
        "started": True,
        "reason": "spawned",
        "pid": process.pid,
        "prompt_path": str(prompt_path),
        "log_path": str(log_path),
        "lock": str(lock),
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
    dry_run: bool,
) -> dict[str, Any]:
    scoped_text, diff_hash = scoped_status(root, scope)
    repo = str(scope["repo"])
    current_head = run_git(root / repo, ["rev-parse", "--short", "HEAD"]) or ""
    log_mtime = recent_log_mtime(root, scope_id)
    previous_scope = ((previous or {}).get("scopes") or {}).get(scope_id, {})
    previous_repo = ((previous or {}).get("repos") or {}).get(repo, {})

    record_exists = bool(
        roster_entry.get("status") in {"running", "active", "completed", "started"}
        or roster_entry.get("agent_id")
        or roster_entry.get("last_started_at")
    )
    lock = lock_status(lock_path(root, scope_id), now)
    previous_log_mtime = previous_scope.get("log_mtime")
    progress = bool(
        previous is None
        or current_head != previous_repo.get("head")
        or diff_hash != previous_scope.get("diff_hash")
        or (log_mtime is not None and log_mtime != previous_log_mtime)
    )
    scope_report_path = report_path(root, scope_id)
    if scope_report_path and scope_report_path.exists():
        report_mtime = scope_report_path.stat().st_mtime
        if report_mtime != previous_scope.get("report_mtime"):
            progress = True
    else:
        report_mtime = None

    if same_hour:
        stalled_count = int(previous_scope.get("stalled_count", 0))
    else:
        stalled_count = 0 if progress else int(previous_scope.get("stalled_count", 0)) + 1

    actions: list[dict[str, Any]] = []
    action_reason = ""
    should_start = False
    completed = roster_entry.get("status") == "completed"
    continuous = bool(scope.get("continuous"))
    if completed and not continuous:
        stalled_count = 0
    if continuous:
        last_started = parse_iso(roster_entry.get("last_started_at") if isinstance(roster_entry.get("last_started_at"), str) else None)
        started_this_hour = bool(last_started and hour_bucket(last_started) == hour_bucket(now))
        if not started_this_hour:
            should_start = True
            action_reason = "scheduled hourly continuous scope"
    elif completed:
        should_start = False
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
            prompt=fallback_prompt(scope_id, scope, action_reason),
            cwd=root / repo,
            codex_bin=codex_bin,
            dry_run=dry_run,
        )
        actions.append({"type": "start-fallback-agent", "reason": action_reason, "result": launch})
        if launch.get("started"):
            roster_entry["status"] = "started"
            roster_entry["last_started_at"] = iso(now)
            roster_entry["last_start_reason"] = action_reason
            roster_entry["fallback_log_path"] = launch.get("log_path")

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
        "report_mtime": report_mtime,
        "last_seen_at": roster_entry.get("last_seen_at"),
        "progress": progress,
        "stalled_count": stalled_count,
        "lock": lock,
        "actions": actions,
    }


def maybe_start_manager(
    *,
    root: Path,
    manager: dict[str, Any],
    codex_bin: str,
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
            prompt=manager_prompt(reason),
            cwd=root,
            codex_bin=codex_bin,
            dry_run=dry_run,
        ),
    }


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    now = utcnow()
    current_bucket = hour_bucket(now)
    root = Path(args.root).resolve()
    agents_dir = root / ".agents"
    snapshot_dir = agents_dir / "hourly-snapshots"
    roster_path = Path(args.roster).resolve() if args.roster else agents_dir / "agent-roster.json"
    summary_path = Path(args.summary_file).resolve() if args.summary_file else agents_dir / "last-watchdog-summary.json"

    if not args.dry_run:
        agents_dir.mkdir(parents=True, exist_ok=True)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

    roster = merge_roster(read_json(roster_path, {}), now)
    latest_snapshot = load_previous_snapshot(snapshot_dir)
    previous = load_previous_distinct_snapshot(snapshot_dir, current_bucket) or latest_snapshot
    same_hour = bool(latest_snapshot and snapshot_bucket(latest_snapshot) == current_bucket)
    repos = {name: collect_repo(root, name, now) for name in DEFAULT_REPOS}
    manager = collect_manager(root, now, args.manager_stale_minutes)
    systemd_mail = collect_systemd_mail(now)
    actions: list[dict[str, Any]] = []
    manager_action = maybe_start_manager(root=root, manager=manager, codex_bin=args.codex_bin, dry_run=args.dry_run)
    if manager_action:
        actions.append(manager_action)

    scopes: dict[str, Any] = {}
    for scope_id, scope in DEFAULT_SCOPES.items():
        entry = roster["scopes"].setdefault(scope_id, {})
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
            dry_run=args.dry_run,
        )
        entry["last_seen_at"] = iso(now)
        entry["last_head"] = scopes[scope_id]["head"]
        entry["last_diff_hash"] = scopes[scope_id]["diff_hash"]
        entry["last_stalled_count"] = scopes[scope_id]["stalled_count"]
        actions.extend(scopes[scope_id]["actions"])

    summary = {
        "version": 1,
        "generated_at": iso(now),
        "hour_bucket": current_bucket,
        "root": str(root),
        "dry_run": bool(args.dry_run),
        "manager": manager,
        "systemd_mail": systemd_mail,
        "reports": collect_reports(root),
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
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    summary = build_summary(args)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
