#!/usr/bin/env python3
"""Send an hourly multi-repository development progress summary.

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
    commits = run_git(repo, ["log", "--since=1 hour ago", "--oneline", "--max-count=5"])
    dirty = [line for line in status.splitlines() if line and not line.startswith("## ")]
    upstream = next((line for line in status.splitlines() if line.startswith("## ")), "## status unavailable")
    commit_text = "; ".join(commits.splitlines()) if commits and commits != "(no output)" else "no commits in last hour"
    dirty_text = "clean" if not dirty else f"{len(dirty)} dirty: " + "; ".join(dirty[:5])
    return f"- {name}: {branch or '(unknown)'} {head or '(no head)'} {upstream}; {dirty_text}; {commit_text}"


def watchdog_lines(summary: dict[str, object]) -> list[str]:
    if not summary:
        return ["Watchdog: no summary file found"]

    manager = summary.get("manager") if isinstance(summary.get("manager"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    failures = summary.get("failures") if isinstance(summary.get("failures"), list) else []
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    systemd_mail = summary.get("systemd_mail") if isinstance(summary.get("systemd_mail"), dict) else {}
    reports = summary.get("reports") if isinstance(summary.get("reports"), dict) else {}

    lines = [
        f"Watchdog generated: {summary.get('generated_at', '(unknown)')}",
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

    if scopes:
        lines.append("")
        lines.append("Agent 状态:")
        for scope_id, raw_scope in sorted(scopes.items()):
            scope = raw_scope if isinstance(raw_scope, dict) else {}
            action_count = len(scope.get("actions", [])) if isinstance(scope.get("actions"), list) else 0
            lines.append(
                "- "
                f"{scope_id}: status={scope.get('status', 'unknown')} "
                f"progress={scope.get('progress', 'unknown')} "
                f"stalled={scope.get('stalled_count', 'unknown')} "
                f"repo={scope.get('repo', 'unknown')} "
                f"actions={action_count}"
            )

    change_summary = reports.get("change_summary") if isinstance(reports.get("change_summary"), dict) else {}
    plan_audit = reports.get("plan_audit") if isinstance(reports.get("plan_audit"), dict) else {}
    if change_summary.get("text"):
        lines.append("")
        lines.append("中文功能摘要:")
        lines.append(str(change_summary.get("text", "")).strip())
    if plan_audit.get("text"):
        lines.append("")
        lines.append("计划方向审计:")
        lines.append(str(plan_audit.get("text", "")).strip())

    if actions:
        lines.append("")
        lines.append("Watchdog actions:")
        for action in actions[:10]:
            if not isinstance(action, dict):
                continue
            result = action.get("result") if isinstance(action.get("result"), dict) else {}
            lines.append(
                "- "
                f"{action.get('type', 'action')}: {action.get('reason', '')} "
                f"started={result.get('started', False)} "
                f"result={result.get('reason', result.get('pid', ''))}"
            )

    return lines


def build_body(root: Path, repos: tuple[str, ...]) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    sections = [summarize_repo(root, repo) for repo in repos]
    return "\n".join(
        [
            f"gotouhou hourly development update",
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
        "gotouhou 每小时开发简报",
        f"Generated: {now}",
        f"Workspace: {root}",
        f"Watchdog summary: {watchdog_summary_path}",
        "",
        *watchdog_lines(watchdog),
        "",
        "服务器状态:",
        *repo_lines,
        "",
        "Agent 提示词位置:",
        "- 当前运行/补救提示词: /root/gotouhou/.agents/prompts/",
        "- 中文摘要 agent 提示词: /root/gotouhou/.agents/agent-prompts/change-describer.md",
        "- 方向审计 agent 提示词: /root/gotouhou/.agents/agent-prompts/plan-auditor.md",
        "",
        "说明:",
        "- 网络/协议相关变更继续由 docs/ops/protocol_audit_check.py 审计。",
        "- SMTP 密码只在主机环境文件中读取，不会写入邮件正文或 git。",
    ]
    return "\n".join(lines)


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
    subject = f"[gotouhou] hourly development update {now}"
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
