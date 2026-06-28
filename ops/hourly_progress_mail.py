#!/usr/bin/env python3
"""Send an hourly multi-repository development progress summary.

The script is intentionally dependency-free so it can run from cron or a
systemd timer on a development host. SMTP credentials are read from the
environment and are never stored in the repository.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path


DEFAULT_REPOS = ("docs", "SpellKard", "Gensoulkyo", "PhK-BattleServer", "PhK-Protocol")


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
