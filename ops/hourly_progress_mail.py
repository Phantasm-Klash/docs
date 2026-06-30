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
import re
import smtplib
import subprocess
import sys
from email.message import EmailMessage
from pathlib import Path


DEFAULT_REPOS = ("docs", "SpellKard", "Gensoulkyo", "PhK-BattleServer", "PhK-Protocol")
DEFAULT_WATCHDOG_SUMMARY = "/root/gotouhou/.agents/last-watchdog-summary.json"
DEFAULT_AUDIT_REPORT = "/root/gotouhou/.agents/reports/audit-agent-latest.md"
REPORT_INTERVAL_HOURS = 3
PROJECT_COMPLETION_PERCENT = 38
UTC_PLUS_8 = dt.timezone(dt.timedelta(hours=8))


def format_time_cn(value: object) -> str:
    parsed: dt.datetime | None = None
    if isinstance(value, str) and value:
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            parsed = None
    if parsed is None:
        parsed = dt.datetime.now(dt.timezone.utc)
    return parsed.astimezone(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M:%S UTC+8")


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


def record_risk_description(record_id: str, record: dict[str, object]) -> str:
    lock = record.get("lock") if isinstance(record.get("lock"), dict) else {}
    log = record.get("log") if isinstance(record.get("log"), dict) else {}
    reasons: list[str] = []
    if lock.get("stale"):
        reasons.append("lock 过期")
    if lock.get("dead_unfinished"):
        reasons.append("死锁/异常退出未完成")
    if lock.get("alive") and not log.get("useful_hash"):
        reasons.append("已启动但暂无有效输出")
    if record.get("report_expected") and not record.get("report_updated"):
        reasons.append("报告未更新")
    if record.get("version_blocked"):
        reasons.append("agent 已退出但仍有未提交改动，版本流程未完成")
    if record.get("failed_runtime"):
        reasons.append("fallback 非零退出")
    if record.get("idle_until_next_hour"):
        reasons.append(f"当前 {REPORT_INTERVAL_HOURS} 小时窗口已完成，等待下个窗口继续 /goal")
    stalled_count = int(record.get("stalled_count", 0) or 0)
    if stalled_count >= 2:
        reasons.append("连续两次无有效提交、日志、心跳或测试信号")
    elif not record.get("progress"):
        reasons.append("本轮无有效提交、日志、心跳或测试信号")
    if record.get("recent_launch_failed"):
        reasons.append("上次补救无有效输出")
    if not reasons:
        return ""
    return f"{record_id}: " + "；".join(reasons)


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
        return ["- Agent summary: no summary file found"]
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    records = agents or scopes
    regression = summary.get("regression") if isinstance(summary.get("regression"), dict) else {}
    pull_requests = summary.get("pull_requests") if isinstance(summary.get("pull_requests"), dict) else {}
    pull_request_queue = summary.get("pull_request_queue") if isinstance(summary.get("pull_request_queue"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    active = [
        record_id
        for record_id, raw_record in records.items()
        if isinstance(raw_record, dict) and ((raw_record.get("lock") or {}).get("alive") or raw_record.get("status") == "running")
    ]
    failed_or_blocked = [
        record_id
        for record_id, raw_record in records.items()
        if isinstance(raw_record, dict)
        and (
            raw_record.get("status") in {"failed", "blocked"}
            or raw_record.get("failed_runtime")
            or raw_record.get("recent_launch_failed")
            or raw_record.get("version_blocked")
        )
    ]
    pr_text = pull_request_summary_text(pull_requests)
    if pull_request_queue:
        pr_text = (
            f"{pull_request_queue.get('open_count', pr_text)}"
            f"（needs_action={pull_request_queue.get('needs_action_count', 'unknown')}，"
            f"ready={pull_request_queue.get('ready_count', 'unknown')}）"
        )
    return [
        f"- 生成时间：{format_time_cn(summary.get('generated_at'))}",
        f"- 整体完成度：约 {PROJECT_COMPLETION_PERCENT}%。",
        "- 当前阶段：Phase 3，服务器权威在线 MVP 与服务拆分收敛。",
        f"- 回归状态：ok={regression.get('ok', 'unknown')}，failed={regression.get('failed_count', 'unknown')}。",
        f"- Active agent：{', '.join(sorted(active)) if active else '无'}。",
        f"- Failed/blocked agent：{', '.join(sorted(failed_or_blocked)) if failed_or_blocked else '无'}。",
        f"- Open PR：{pr_text}；manager actions={len(actions)}；本轮启动={summary.get('started_count', 0)}。",
    ]


def pull_request_summary_text(pull_requests: dict[str, object]) -> str:
    open_pr_count = 0
    failed_repos: list[str] = []
    for repo_name, raw_repo in sorted(pull_requests.items()):
        repo = raw_repo if isinstance(raw_repo, dict) else {}
        count = repo.get("open_count")
        if isinstance(count, int):
            open_pr_count += count
        else:
            failed_repos.append(str(repo.get("repo") or repo_name))
    if failed_repos:
        return (
            "未知"
            f"（{len(failed_repos)} 个仓库采集失败：{'、'.join(failed_repos[:10])}；"
            f"已采集可见 {open_pr_count}）"
        )
    return str(open_pr_count)


def pull_request_queue_lines(summary: dict[str, object], *, limit: int = 8) -> list[str]:
    queue = summary.get("pull_request_queue") if isinstance(summary.get("pull_request_queue"), dict) else {}
    if not queue:
        return ["- 未读取到结构化 PR 行动队列；仅使用 open PR 数。"]
    failed_repos = queue.get("failed_repos") if isinstance(queue.get("failed_repos"), list) else []
    lines = [
        (
            "- "
            f"open={queue.get('open_count', 0)}；"
            f"needs_action={queue.get('needs_action_count', 0)}；"
            f"ready={queue.get('ready_count', 0)}；"
            f"by_repo={queue.get('by_repo', {})}；"
            f"by_state={queue.get('by_merge_state', {})}；"
            f"by_owner={queue.get('by_owner_agent', {})}；"
            f"by_action={queue.get('by_action_category', {})}；"
            f"supersede_groups={queue.get('supersede_group_count', 0)}"
        )
    ]
    if failed_repos:
        lines.append(f"- PR 采集失败仓库：{'、'.join(str(item) for item in failed_repos[:10])}")

    def check_detail(checks: dict[str, object]) -> str:
        parts: list[str] = []
        for key, label in (("failed_checks", "failed"), ("pending_checks", "pending")):
            names = checks.get(key) if isinstance(checks.get(key), list) else []
            if names:
                rendered = ", ".join(str(name) for name in names[:3])
                if len(names) > 3:
                    rendered += f", +{len(names) - 3}"
                parts.append(f"{label}=[{rendered}]")
        return "；" + "；".join(parts) if parts else ""

    def review_gate_detail(item: dict[str, object]) -> str:
        gate = item.get("review_gate") if isinstance(item.get("review_gate"), dict) else {}
        if not gate.get("required"):
            return ""
        category = str(gate.get("category") or "review")
        reason = str(gate.get("reason") or "").strip()
        return f"；review_gate={category}" + (f"：{reason}" if reason else "")

    groups = queue.get("supersede_groups") if isinstance(queue.get("supersede_groups"), list) else []
    for raw_group in groups[:4]:
        group = raw_group if isinstance(raw_group, dict) else {}
        lines.append(
            "- "
            f"{group.get('owner_agent', 'unknown')} -> {group.get('repo')} stale group："
            f"count={group.get('count')}；prs={group.get('numbers')}；"
            f"states={group.get('merge_states')}；{group.get('action')}"
        )
    ready_items = queue.get("merge_ready_items") if isinstance(queue.get("merge_ready_items"), list) else []
    for raw_item in ready_items[:6]:
        item = raw_item if isinstance(raw_item, dict) else {}
        checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
        lines.append(
            "- "
            f"merge-ready {item.get('owner_agent', 'unknown')} -> {item.get('repo')} #{item.get('number')}："
            f"checks ok/fail/pending={checks.get('success', 0)}/{checks.get('failed', 0)}/{checks.get('pending', 0)}；"
            f"{item.get('url')}{check_detail(checks)}{review_gate_detail(item)}"
        )
    items = queue.get("top_items") if isinstance(queue.get("top_items"), list) else []
    if not items:
        open_count = int(queue.get("open_count", 0) or 0)
        if open_count:
            lines.append("- 当前没有可展示的 top PR 明细；请查看结构化 PR 队列。")
        else:
            lines.append("- 当前没有 open PR。")
        return lines
    for raw_item in items[:limit]:
        item = raw_item if isinstance(raw_item, dict) else {}
        checks = item.get("checks") if isinstance(item.get("checks"), dict) else {}
        lines.append(
            "- "
            f"{item.get('owner_agent', 'unknown')} -> {item.get('repo')} #{item.get('number')}：{item.get('merge_state')}；"
            f"checks ok/fail/pending={checks.get('success', 0)}/{checks.get('failed', 0)}/{checks.get('pending', 0)}；"
            f"{item.get('action_category', 'inspect')}:{item.get('action')}；{item.get('url')}"
            f"{check_detail(checks)}{review_gate_detail(item)}"
        )
    return lines


def cn_agent_status(value: object) -> str:
    mapping = {
        "started": "运行中",
        "running": "运行中",
        "active": "运行中",
        "completed": "已完成",
        "blocked": "阻塞",
        "failed": "失败",
        "unknown": "未知",
    }
    return mapping.get(str(value), str(value))


def agent_status_lines(summary: dict[str, object]) -> list[str]:
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    scopes = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
    records = agents or scopes
    if not records:
        return ["- 未读取到 agent 状态。"]
    lines: list[str] = []
    for agent_id, raw_agent in sorted(records.items()):
        agent = raw_agent if isinstance(raw_agent, dict) else {}
        lock = agent.get("lock") if isinstance(agent.get("lock"), dict) else {}
        runtime_log = agent.get("runtime_log") if isinstance(agent.get("runtime_log"), dict) else {}
        token_usage = runtime_log.get("token_usage")
        token_text = f"{int(token_usage):,}" if isinstance(token_usage, int) else "未知"
        elapsed = runtime_log.get("elapsed") or "未知"
        state = cn_agent_status(agent.get("status", "unknown"))
        if lock.get("alive"):
            state = "运行中"
        elif agent.get("version_blocked"):
            state = "版本阻塞"
        elif agent.get("failed_runtime") or agent.get("recent_launch_failed"):
            state = "失败"
        deferred = agent.get("deferred_reason") if agent.get("deferred") else ""
        extra = f"；暂缓：{deferred}" if deferred else ""
        lines.append(
            f"- {agent_id}：{state}；repo={agent.get('repo', 'unknown')}；"
            f"tokens={token_text}；耗时={elapsed}；progress={bool_cn(agent.get('progress'))}{extra}"
        )
    return lines


def agent_resource_risk_lines(summary: dict[str, object], *, limit: int = 6) -> list[str]:
    risk = summary.get("agent_resource_risk") if isinstance(summary.get("agent_resource_risk"), dict) else {}
    if not risk:
        return ["- 未读取到结构化 agent 资源风险；详见 agent 状态行。"]
    lines = [
        (
            "- "
            f"high={risk.get('high_count', 0)}；"
            f"medium={risk.get('medium_count', 0)}；"
            f"thresholds={risk.get('thresholds', {})}"
        )
    ]
    items = risk.get("top_items") if isinstance(risk.get("top_items"), list) else []
    if not items:
        lines.append("- 当前没有可展示的资源风险项。")
        return lines
    for raw_item in items[:limit]:
        item = raw_item if isinstance(raw_item, dict) else {}
        token_usage = item.get("token_usage")
        token_text = f"{int(token_usage):,}" if isinstance(token_usage, int) else "未知"
        lines.append(
            "- "
            f"{item.get('agent')}：{item.get('severity')}；"
            f"tokens={token_text}；"
            f"log_bytes={item.get('log_bytes', 'unknown')}；"
            f"{item.get('action', '')}"
        )
    return lines


def section_lines_from_report(text: str, headings: tuple[str, ...], *, limit: int = 8) -> list[str]:
    if not text:
        return []
    lines = text.splitlines()
    wanted: list[str] = []
    active = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            active = any(name in stripped for name in headings)
            continue
        if active and stripped.startswith("- "):
            wanted.append(stripped)
        if len(wanted) >= limit:
            break
    return wanted


def audited_update_lines(summary: dict[str, object]) -> list[str]:
    reports = summary.get("reports") if isinstance(summary.get("reports"), dict) else {}
    audit_report = reports.get("audit_report") if isinstance(reports.get("audit_report"), dict) else {}
    change = reports.get("change_summary") if isinstance(reports.get("change_summary"), dict) else {}
    audit = reports.get("plan_audit") if isinstance(reports.get("plan_audit"), dict) else {}
    lines = []
    lines.extend(section_lines_from_report(str(audit_report.get("text", "")), ("结论", "新 agent 状态", "Git 与版本风险", "下个三小时方向"), limit=10))
    lines.extend(section_lines_from_report(str(change.get("text", "")), ("本轮新增", "审计到的更新", "版本管理状态", "阻塞/风险"), limit=6))
    lines.extend(section_lines_from_report(str(audit.get("text", "")), ("风险", "流程判断", "阶段判断"), limit=5))
    if not lines:
        actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
        for action in actions[:6]:
            if isinstance(action, dict):
                lines.append(f"- {action.get('agent') or action.get('repo') or 'manager'}：{action.get('reason', action.get('type', '已更新'))}")
    if not lines:
        lines.append("- 本轮未审计到新的可汇报更新；继续按 docs/dev Phase 3 主线推进。")
    return lines[:10]


def latest_audit_report_lines(root: Path, summary: dict[str, object]) -> list[str]:
    report_path = Path(DEFAULT_AUDIT_REPORT)
    if not report_path.is_absolute():
        report_path = root / report_path
    text = ""
    try:
        text = report_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        pass
    if not text:
        reports = summary.get("reports") if isinstance(summary.get("reports"), dict) else {}
        audit_report = reports.get("audit_report") if isinstance(reports.get("audit_report"), dict) else {}
        text = str(audit_report.get("text", ""))
    lines = section_lines_from_report(text, ("结论", "新 agent 状态", "Git 与版本风险", "下个三小时方向"), limit=10)
    return lines or audited_update_lines(summary)


def watchdog_lines(summary: dict[str, object]) -> list[str]:
    if not summary:
        return ["Watchdog: no summary file found"]

    manager = summary.get("manager") if isinstance(summary.get("manager"), dict) else {}
    actions = summary.get("actions") if isinstance(summary.get("actions"), list) else []
    failures = summary.get("failures") if isinstance(summary.get("failures"), list) else []
    agents = summary.get("agents") if isinstance(summary.get("agents"), dict) else {}
    legacy_records = summary.get("scopes") if isinstance(summary.get("scopes"), dict) else {}
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

    if agents:
        lines.append("")
        lines.append("Agent 最终状态:")
        for agent_id, raw_agent in sorted(agents.items()):
            agent = raw_agent if isinstance(raw_agent, dict) else {}
            lock = agent.get("lock") if isinstance(agent.get("lock"), dict) else {}
            unit_info = lock.get("unit_info") if isinstance(lock.get("unit_info"), dict) else {}
            risk = record_risk_description(agent_id, agent)
            lines.append(
                "- "
                f"{agent_id}: status={agent.get('status', 'unknown')} "
                f"repo={agent.get('repo', 'unknown')} "
                f"progress={agent.get('progress', 'unknown')} "
                f"lock_alive={lock.get('alive', 'unknown')} "
                f"unit={lock.get('unit') or '-'} "
                f"unit_active={unit_info.get('active', lock.get('unit_active', 'unknown'))}"
            )
            if risk:
                lines.append(f"  风险: {risk}")

    if legacy_records and not agents:
        lines.append("")
        lines.append("旧记录最终状态:")
        for record_id, raw_record in sorted(legacy_records.items()):
            record = raw_record if isinstance(raw_record, dict) else {}
            action_count = len(record.get("actions", [])) if isinstance(record.get("actions"), list) else 0
            lock = record.get("lock") if isinstance(record.get("lock"), dict) else {}
            unit_info = lock.get("unit_info") if isinstance(lock.get("unit_info"), dict) else {}
            risk = record_risk_description(record_id, record)
            lines.append(
                "- "
                f"{record_id}: status={record.get('status', 'unknown')} "
                f"progress={record.get('progress', 'unknown')} "
                f"repo={record.get('repo', 'unknown')} "
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
    now = format_time_cn(None)
    watchdog = read_json(watchdog_summary_path)
    lines = [
        f"gotouhou {REPORT_INTERVAL_HOURS}小时开发简报",
        f"Generated: {now}",
        f"Workspace: {root}",
        f"Agent summary: {watchdog_summary_path}",
        "",
        "项目进度:",
        *minimal_watchdog_lines(watchdog),
        "",
        "服务器状态:",
        *agent_status_lines(watchdog),
        "",
        "Agent 资源风险:",
        *agent_resource_risk_lines(watchdog),
        "",
        "审计 agent 汇报:",
        *latest_audit_report_lines(root, watchdog),
        "",
        "PR 行动队列:",
        *pull_request_queue_lines(watchdog),
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
    now = dt.datetime.now(UTC_PLUS_8).strftime("%Y-%m-%d %H:%M UTC+8")
    subject = f"[gotouhou] {REPORT_INTERVAL_HOURS}小时开发简报 {now}"
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
