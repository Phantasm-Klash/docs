#!/usr/bin/env python3
"""Send a periodic multi-repository development progress summary.

The script is intentionally dependency-free so it can run from cron or a
systemd timer on a development host. SMTP credentials are read from the
environment and are never stored in the repository.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path


DEFAULT_REPOS = ("docs", "SpellKard", "Gensoulkyo", "PhK-BattleServer", "PhK-Protocol")
DEFAULT_WATCHDOG_SUMMARY = "/root/gotouhou/.agents/last-watchdog-summary.json"
REPORT_INTERVAL_HOURS = 3
PROJECT_COMPLETION_PERCENT = 38


def run_git(repo: Path, args: list[str]) -> str:
    if not (repo / ".git").exists():
        return "not a git repository on this host"
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), *args],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=20,
        )
    except subprocess.SubprocessError as exc:
        return f"git command failed: {exc}"
    return completed.stdout.strip() or "(no output)"


def read_json(path: Path) -> dict[str, object]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return value if isinstance(value, dict) else {}


def bool_cn(value: object) -> str:
    if value is True:
        return "是"
    if value is False:
        return "否"
    return str(value)


def scope_risk_description(scope_id: str, scope: dict[str, object]) -> str:
    lock = scope.get("lock") if isinstance(scope.get("lock"), dict) else {}
    log = scope.get("log") if isinstance(scope.get("log"), dict) else {}
    reasons: list[str] = []
    if lock.get("stale"):
        reasons.append("lock 过期")
    if lock.get("dead_unfinished"):
        reasons.append("死锁/异常退出未完成")
    if lock.get("alive") and not log.get("useful_hash"):
        reasons.append("已启动但暂无有效输出")
    if scope.get("report_expected") and not scope.get("report_updated"):
        reasons.append("报告未更新")
    if scope.get("version_blocked"):
        reasons.append("agent 已退出但 scope 路径仍有未提交改动，版本流程未完成")
    if scope.get("failed_runtime"):
        reasons.append("fallback 非零退出")
    if scope.get("idle_until_next_hour"):
        reasons.append(f"当前 {REPORT_INTERVAL_HOURS} 小时窗口已完成，等待下个窗口继续 /goal")
    stalled_count = int(scope.get("stalled_count", 0) or 0)
    if stalled_count >= 2:
        reasons.append("连续两次无 scoped diff/commit/scope heartbeat/test signal")
    elif not scope.get("progress"):
        reasons.append("本轮无 scoped diff/commit/scope heartbeat/test signal")
    if scope.get("recent_launch_failed"):
        reasons.append("上次补救无有效输出")
    if not reasons:
        return ""
    return f"{scope_id}: " + "；".join(reasons)


def summarize_repo(root: Path, name: str) -> str:
    repo = root / name
    if not repo.exists():
        return f"## {name}\nmissing at {repo}\n"

    branch = run_git(repo, ["branch", "--show-current"])
    status = run_git(repo, ["status", "--short", "--branch"])
    recent = run_git(repo, ["log", "--oneline", "--decorate", "-5"])
    diffstat = run_git(repo, ["diff", "--stat"])

    return "\n".join(
        [
            f"## {name}",
            f"Path: {repo}",
            f"Branch: {branch}",
            "",
            "Status:",
            status,
            "",
            "Recent commits:",
            recent,
            "",
            "Uncommitted diffstat:",
            diffstat,
            "",
        ]
    )


def summarize_repo_brief(root: Path, name: str) -> str:
    repo = root / name
    if not repo.exists():
        return f"- {name}: missing at {repo}"

    branch = run_git(repo, ["branch", "--show-current"])
    head = run_git(repo, ["rev-parse", "--short", "HEAD"])
    status = run_git(repo, ["status", "--short", "--branch"])
    commits = run_git(repo, ["log", f"--since={REPORT_INTERVAL_HOURS} hours ago", "--oneline", "--max-count=5"])
    dirty = [line for line in status.splitlines() if line and not line.startswith("## ")]
    upstream = next((line for line in status.splitlines() if line.startswith("## ")), "## status unavailable")
    commit_text = "; ".join(commits.splitlines()) if commits and commits != "(no output)" else f"no commits in last {REPORT_INTERVAL_HOURS}h"
    dirty_text = "clean" if not dirty else f"{len(dirty)} dirty: " + "; ".join(dirty[:5])
    return f"- {name}: {branch or '(unknown)'} {head or '(no head)'} {upstream}; {dirty_text}; {commit_text}"


def minimal_watchdog_lines(summary: dict[str, object]) -> list[str]:
    if not summary:
        return ["- Watchdog: no summary file found"]
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    regression = summary.get("regression") if isinstance(summary.get("regression"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    active = [
        scope_id
        for scope_id, raw_scope in scopes.items()
        if isinstance(raw_scope, dict) and (raw_scope.get("lock") or {}).get("alive")
    ]
    failed_or_blocked = [
        scope_id
        for scope_id, raw_scope in scopes.items()
        if isinstance(raw_scope, dict) and (raw_scope.get("failed_runtime") or raw_scope.get("recent_launch_failed") or raw_scope.get("version_blocked"))
    ]
    open_pr_count = 0
    pr_unknown = False
    for raw_repo in pull_requests.values():
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        count = repo.get("open_count")
        if isinstance(count, int):
            open_pr_count += count
        else:
            pr_unknown = True
    return [
        f"- Generated: {summary.get('generated_at', '(unknown)')}",
        f"- Overall progress: about {PROJECT_COMPLETION_PERCENT}%",
        "- Current phase: Phase 3, server-authoritative online MVP and server split convergence",
        f"- Regression: ok={regression.get('ok', 'unknown')} failed={regression.get('failed_count', 'unknown')}",
        f"- Active agents: {', '.join(sorted(active)) if active else 'none'}",
        f"- Failed/blocked agents: {', '.join(sorted(failed_or_blocked)) if failed_or_blocked else 'none'}",
        f"- Open PRs: {'unknown' if pr_unknown else open_pr_count}; watchdog actions={len(actions)}; started={summary.get('started_count', 0)}",
    ]


def watchdog_lines(summary: dict[str, object]) -> list[str]:
    if not summary:
        return ["Watchdog: no summary file found"]

    manager = summary.get("manager") if isinstance(summary.get("manager"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    failures = summary.get("failures") if isinstance(summary.get("failures"), list) else []
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    systemd_mail = summary.get("systemd_mail") if isinstance(summary.get("systemd_mail"), dict) else {}
    reports = summary.get("reports") if isinstance(summary.get("reports"), dict) else {}
    keyring = summary.get("keyring") if isinstance(summary.get("keyring"), dict) else {}
    key_assignments = summary.get("key_assignments") if isinstance(summary.get("key_assignments"), dict) else {}
    runtime = summary.get("runtime") if isinstance(summary.get("runtime"), dict) else {}
    godot = runtime.get("godot_linux") if isinstance(runtime.get("godot_linux"), dict) else {}
    docker = runtime.get("docker") if isinstance(runtime.get("docker"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}
    regression = summary.get("regression") if isinstance(summary.get("regression"), dict) else {}

    lines = [
        f"Watchdog generated: {summary.get('generated_at', '(unknown)')}",
        f"Watchdog final resample: {bool_cn(summary.get('resampled_after_actions', False))}",
        (
            "Manager: "
            f"mode={manager.get('mode', 'unknown')} "
            f"stale={manager.get('stale', 'unknown')} "
            f"age_seconds={manager.get('age_seconds', 'unknown')}"
        ),
        (
            "Mail timer: "
            f"active={systemd_mail.get('timer_active', 'unknown')} "
            f"enabled={systemd_mail.get('timer_enabled', 'unknown')}"
        ),
        f"Actions: total={len(actions)} started={summary.get('started_count', 0)} failures={len(failures)}",
    ]

    if keyring:
        warning = " permissions-too-open" if keyring.get("permission_warning") else ""
        lines.append(
            "Agent keys: "
            f"source={keyring.get('source', 'configured-local-keyring')} "
            f"aliases={keyring.get('alias_count', 0)} "
            f"mode={keyring.get('permissions', 'unknown')}"
            f"{warning}"
        )
    if key_assignments:
        lines.append("")
        lines.append("Agent key alias 分配:")
        for scope_id, raw_assignment in sorted(key_assignments.items()):
            assignment = raw_assignment if isinstance(raw_assignment, dict) else {}
            lines.append(f"- {scope_id}: {assignment.get('alias') or '(missing)'}")

    if runtime:
        lines.append("")
        lines.append("运行环境:")
        lines.append(
            "- Godot Linux: "
            f"exists={godot.get('exists', 'unknown')} "
            f"executable={godot.get('executable', 'unknown')} "
            f"version={godot.get('version', 'unknown')} "
            f"path={godot.get('path', '')}"
        )
        lines.append(
            "- Docker: "
            f"available={docker.get('available', 'unknown')} "
            f"docker-compose={docker.get('docker_compose_available', 'unknown')} "
            f"version={docker.get('docker_compose_version', 'unknown')}"
        )
        repo_files = docker.get("repo_files") if isinstance(docker.get("repo_files"), dict) else {}
        if repo_files:
            lines.append("- Docker files: " + "; ".join(f"{repo}={len(files)}" for repo, files in sorted(repo_files.items())))

    if pull_requests:
        lines.append("")
        lines.append("PR 状态:")
        for repo_name, raw_prs in sorted(pull_requests.items()):
            prs = raw_prs if isinstance(raw_prs, dict) else {}
            line = f"- {repo_name}: open={prs.get('open_count', 'unknown')}"
            if prs.get("error"):
                line += f" error={prs.get('error')}"
            lines.append(line)
            items = prs.get("items") if isinstance(prs.get("items"), list) else []
            for item in items[:5]:
                if isinstance(item, dict):
                    lines.append(
                        f"  PR #{item.get('number')} {item.get('headRefName')} -> {item.get('baseRefName')} "
                        f"mergeState={item.get('mergeStateStatus')} {item.get('url')}"
                    )

    if regression:
        lines.append("")
        lines.append("回归检查:")
        if regression.get("missing"):
            lines.append(f"- missing: {regression.get('path', '')}")
        else:
            lines.append(
                "- "
                f"ok={regression.get('ok', 'unknown')} "
                f"failed_count={regression.get('failed_count', 'unknown')} "
                f"generated_at={regression.get('generated_at', 'unknown')}"
            )
            failed = regression.get("failed") if isinstance(regression.get("failed"), list) else []
            for item in failed[:8]:
                if isinstance(item, dict):
                    lines.append(f"- failed: {item.get('name')} status={item.get('status')} blocked={item.get('blocked', False)}")

    if scopes:
        lines.append("")
        lines.append("Agent 最终状态:")
        for scope_id, raw_scope in sorted(scopes.items()):
            scope = raw_scope if isinstance(raw_scope, dict) else {}
            action_count = len(scope.get("actions", [])) if isinstance(scope.get("actions"), list) else 0
            lock = scope.get("lock") if isinstance(scope.get("lock"), dict) else {}
            unit_info = lock.get("unit_info") if isinstance(lock.get("unit_info"), dict) else {}
            risk = scope_risk_description(scope_id, scope)
            lines.append(
                "- "
                f"{scope_id}: status={scope.get('status', 'unknown')} "
                f"continuous={scope.get('continuous', 'unknown')} "
                f"started_this_hour={scope.get('started_this_hour', 'unknown')} "
                f"due_for_continuation={scope.get('due_for_continuation', 'unknown')} "
                f"runtime_completed={scope.get('completed_runtime', 'unknown')} "
                f"runtime_failed={scope.get('failed_runtime', 'unknown')} "
                f"version_blocked={scope.get('version_blocked', 'unknown')} "
                f"idle_until_next_hour={scope.get('idle_until_next_hour', 'unknown')} "
                f"progress={scope.get('progress', 'unknown')} "
                f"stalled={scope.get('stalled_count', 'unknown')} "
                f"deferred={scope.get('deferred', False)} "
                f"deferred_reason={scope.get('deferred_reason') or '-'} "
                f"repo={scope.get('repo', 'unknown')} "
                f"lock_alive={lock.get('alive', 'unknown')} "
                f"unit={lock.get('unit') or '-'} "
                f"unit_active={unit_info.get('active', lock.get('unit_active', 'unknown'))} "
                f"pid_alive={lock.get('stored_pid_alive', 'unknown')} "
                f"actions={action_count}"
            )
            if risk:
                lines.append(f"  风险: {risk}")

    change_summary = reports.get("change_summary") if isinstance(reports.get("change_summary"), dict) else {}
    plan_audit = reports.get("plan_audit") if isinstance(reports.get("plan_audit"), dict) else {}
    if change_summary.get("text"):
        lines.append("")
        lines.append(f"中文功能摘要: updated_at={change_summary.get('updated_at', 'unknown')}")
        lines.append(str(change_summary.get("text", "")).strip())
    if plan_audit.get("text"):
        lines.append("")
        lines.append(f"计划方向审计: updated_at={plan_audit.get('updated_at', 'unknown')}")
        lines.append(str(plan_audit.get("text", "")).strip())

    if actions:
        lines.append("")
        lines.append("Watchdog actions:")
        for action in actions[:10]:
            if not isinstance(action, dict):
                continue
            result = action.get("result") if isinstance(action.get("result"), dict) else {}
            if result:
                lines.append(
                    "- "
                    f"{action.get('type', 'action')}: {action.get('reason', '')} "
                    f"started={result.get('started', False)} "
                    f"result={result.get('reason', result.get('pid', result.get('unit', '')))}"
                )
            else:
                detail = action.get("url") or action.get("lock") or action.get("number") or ""
                lines.append(f"- {action.get('type', 'action')}: {action.get('reason', '')} {detail}")

    return lines


def build_body(root: Path, repos: tuple[str, ...]) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sections = [summarize_repo(root, repo) for repo in repos]
    return "\n".join(
        [
            f"gotouhou {REPORT_INTERVAL_HOURS}h development update",
            f"Generated: {now}",
            f"Workspace: {root}",
            "",
            *sections,
        ]
    )


def build_brief_body(root: Path, repos: tuple[str, ...], watchdog_summary_path: Path) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    watchdog = read_json(watchdog_summary_path)
    repo_lines = [summarize_repo_brief(root, repo) for repo in repos]
    lines = [
        f"gotouhou {REPORT_INTERVAL_HOURS}小时开发简报",
        f"Generated: {now}",
        f"Workspace: {root}",
        f"Watchdog summary: {watchdog_summary_path}",
        "",
        "项目进度:",
        *minimal_watchdog_lines(watchdog),
        "",
        "服务器状态:",
        *repo_lines,
        "",
        "下一步:",
        "- 按 docs/dev 优先级继续 Phase 3：协议、Nakama/PostgreSQL、C++ BattleServer、SpellKard 在线 UI/验证。",
        "- 正在运行的 `/goal` agent 不因汇报周期被打断。",
        "- 简单线性改动不强制 PR；复杂/跨仓/回归/多路验证才走分支 PR。",
    ]
    return "\n".join(lines)


def build_agent_prompt_lines(root: Path) -> list[str]:
    prompt_dir = root / ".agents" / "agent-prompts"
    configured = (
        ("change-describer", prompt_dir / "change-describer.md"),
        ("plan-auditor", prompt_dir / "plan-auditor.md"),
    )
    lines = ["Agent 提示词内容:"]
    for name, path in configured:
        if not path.exists():
            lines.append(f"- {name}: 未找到 {path}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace").strip()
        if len(text) > 1200:
            text = text[:1200].rstrip() + "\n...(已截断)"
        lines.append(f"### {name}\n{text}")
    prompts_dir = root / ".agents" / "prompts"
    if prompts_dir.exists():
        recent = sorted(prompts_dir.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:8]
        if recent:
            lines.append("### 最近补救/运行提示词文件")
            lines.extend(f"- {path.name}" for path in recent)
    return lines


def send_mail(
    *,
    smtp_host: str,
    smtp_port: int,
    smtp_user: str,
    smtp_password: str,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    starttls: bool,
) -> None:
    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=30) as smtp:
        smtp.ehlo()
        if starttls:
            smtp.starttls()
            smtp.ehlo()
        if smtp_user:
            smtp.login(smtp_user, smtp_password)
        smtp.send_message(message)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="/root/gotouhou", help="workspace root")
    parser.add_argument("--repo", action="append", dest="repos", help="repo directory name")
    parser.set_defaults(brief=True)
    parser.add_argument("--brief", action="store_true", help="send a concise watchdog-aware report")
    parser.add_argument("--full", action="store_false", dest="brief", help="send the legacy detailed git report")
    parser.add_argument(
        "--watchdog-summary",
        default=os.getenv("GOTOUHOU_WATCHDOG_SUMMARY", DEFAULT_WATCHDOG_SUMMARY),
        help="path to the watchdog JSON summary",
    )
    parser.add_argument("--dry-run", action="store_true", help="print the email body instead of sending")
    parser.add_argument("--smtp-host", default=os.getenv("GOTOUHOU_SMTP_HOST", "smtp.ym.163.com"))
    parser.add_argument("--smtp-port", type=int, default=int(os.getenv("GOTOUHOU_SMTP_PORT", "25")))
    parser.add_argument("--smtp-user", default=os.getenv("GOTOUHOU_SMTP_USER", ""))
    parser.add_argument("--smtp-password", default=os.getenv("GOTOUHOU_SMTP_PASSWORD", ""))
    parser.add_argument("--smtp-starttls", action="store_true", default=os.getenv("GOTOUHOU_SMTP_STARTTLS") == "1")
    parser.add_argument("--from", dest="sender", default=os.getenv("GOTOUHOU_MAIL_FROM", "gotouhou-progress@localhost"))
    parser.add_argument("--to", dest="recipient", default=os.getenv("GOTOUHOU_MAIL_TO", "wjcwqc@qq.com"))
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve()
    repos = tuple(args.repos) if args.repos else DEFAULT_REPOS
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    subject = f"[gotouhou] {REPORT_INTERVAL_HOURS}h development update {now}"
    if args.brief:
        body = build_brief_body(root, repos, Path(args.watchdog_summary).resolve())
    else:
        body = build_body(root, repos)

    if args.dry_run:
        print(body)
        return 0

    if args.smtp_user and not args.smtp_password:
        print("GOTOUHOU_SMTP_PASSWORD is required when GOTOUHOU_SMTP_USER is set", file=sys.stderr)
        return 2

    send_mail(
        smtp_host=args.smtp_host,
        smtp_port=args.smtp_port,
        smtp_user=args.smtp_user,
        smtp_password=args.smtp_password,
        sender=args.sender,
        recipient=args.recipient,
        subject=subject,
        body=body,
        starttls=args.smtp_starttls,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
