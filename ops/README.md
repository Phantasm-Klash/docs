# gotouhou Ops Helpers

## Goal agents and three-hour progress mail

`goal_agent_manager.py` is the current orchestration entry point. It manages
five sustained Codex `/goal` agents by agent identity only:

- `client-agent`: SpellKard client, core bullet gameplay, UI, replay/practice,
  and client/server protocol alignment.
- `battle-server-agent`: C++ battle server, match room lifecycle, temporary
  battle/Boss instances, authoritative simulation, replay/hash, and settlement
  signing.
- `nakama-server-agent`: Gensoulkyo/Nakama business server, PVP queue, battle
  qualification, lobby/room state, allocation/ticket, callbacks, and audit
  persistence.
- `audit-agent`: Chinese audit of commits, direction, agent status, version
  flow, and the three-hour mail report.
- `project-manager-agent`: project propulsion and automatic coordination. It
  reads `docs/dev`, agent logs, git/PR status, regression results, and blockers;
  then adjusts personas/prompts and turns the plan into executable next slices
  for the client, battle server, Nakama, and audit agents.

The manager no longer uses path-slice scheduling or progress heuristics. Codex
`/goal` mode is responsible for stable iterative work. The manager checks
whether each agent is running, completed, failed, or missing; it starts only
missing/failed/due agents and never interrupts a running goal agent simply
because the report interval arrived. The host runs the manager every 15 minutes
through `gotouhou-goal-agent-manager.timer`; the three-hour mail timer only adds
regression sampling and sends the concise report.

Agent workers are launched with Codex `/goal` sustained-target prompts. The
manager reads per-agent API keys from the host-local `/root/.codex/keys` file.
The file may contain `alias: value` or `alias=value` lines; key values are
injected into child process environment only and are never written to JSON, logs,
email, or git. Current default alias fallbacks are:

- `client-agent`: `spellkard`, then `other`;
- `battle-server-agent`: `phk`, `battle-server`, `battle`, then `other`;
- `nakama-server-agent`: `gensoulkyo`, then `other`;
- `audit-agent`: `audit`, `docs`, `ops`, then `other`.
- `project-manager-agent`: `manager`, `project-manager`, `pm`, `ops`, `docs`,
  then `other`.

Keep `/root/.codex/keys` mode `0600`; the progress email reports only aliases and
permission warnings.

Development workers prioritize finishing the overall project according to
`docs/dev/progress.md`. Pull requests are used when they help parallel review or
risk control, not for every commit:

- simple, single-repo, linear changes may be committed on the current target branch when local policy allows;
- complex branches, multi-path validation, cross-repo protocol/network/security work, regression fixes, and parallel agent work should use `agent/<agent>/<YYYYMMDD-HHMM>` or `fix/<area>` branches plus PRs;
- every verified stage should still be committed separately with tests and remaining risk noted;
- PRs should include summary, tests, risks, protocol/network/security impact, and docs/dev direction notes.

The audit agent samples open PRs across the five repositories and reports which
PRs need review, conflict resolution, tests, or branch-protection handling. PR
approval/merge should happen only after reading the diff, checking docs/dev
direction, and running the relevant gates.

The goal manager also writes a structured `pull_request_queue` section into
`.agents/goal-agent-summary.json`. The brief progress mail prints its open,
needs-action, ready, per-repository, per-owner-agent, per-action-category,
per-merge-state, stale supersede-group counts, and explicit merge-ready PRs
plus the top PRs that need conflict resolution, branch updates, pending checks,
review, or merge. A
supersede group means one repository and owner agent have multiple DIRTY/BEHIND
PRs that should be consolidated into a fresh current-base PR or explicitly
closed as superseded before new work expands. The owner field is a routing hint
for the next agent turn; it does not replace diff review or branch-protection
gates.

The same summary also includes `repo_state_risk`, which routes repository
state that is not visible from PRs alone: dirty worktrees, local branches ahead
or behind their upstream, missing checkouts, and root checkouts left on legacy
agent branches. These entries are folded into `next_agent_actions` so prompts
can tell the owning agent to absorb useful dirty work, push or rebuild local
commits as a current-base PR, or avoid treating a legacy root checkout as the
canonical baseline.

SpellKard workers should use the Linux Godot binary at
`/root/gotouhou/Godot_v4.7-stable_linux.x86_64` for headless checks. Server
workers should prefer Docker regression through `docker-compose`; if a server
repo has no Dockerfile/compose files, the worker must run local regression and
record the Docker gap in the report.
Pure Godot renderer failures caused by a headless server without a GPU may be
marked ignored/blocked. GDScript parse, compile, type, script-load, UI contract,
or bullet contract failures are real regressions and must not be ignored.

`hourly_progress_mail.py` sends a concise goal-agent summary every three
hours to
`wjcwqc@qq.com` through `smtp.ym.163.com:25`. It reads SMTP credentials from
environment variables and does not print or store the password. The summary is
intentionally short and prioritizes the audit-agent report: project completion
percent, current phase, regression status, active/blocked agents, git/version
risk, and next priorities.

Dry run:

```sh
python3 ops/goal_agent_manager.py --dry-run
python3 ops/hourly_progress_mail.py --dry-run
```

Legacy full git report:

```sh
python3 ops/hourly_progress_mail.py --dry-run --full
```

Systemd setup on the development host:

```sh
sudo install -d -m 0750 /etc/gotouhou
sudo install -m 0755 ops/goal_agent_supervisor_runner.sh /root/gotouhou/docs/ops/
sudo install -m 0755 ops/hourly_progress_runner.sh /root/gotouhou/docs/ops/
sudo install -m 0644 ops/gotouhou-goal-agent-manager.service /etc/systemd/system/
sudo install -m 0644 ops/gotouhou-goal-agent-manager.timer /etc/systemd/system/
sudo install -m 0644 ops/gotouhou-hourly-progress.service /etc/systemd/system/
sudo install -m 0644 ops/gotouhou-hourly-progress.timer /etc/systemd/system/
sudo editor /etc/gotouhou/progress-mail.env
sudo systemctl daemon-reload
sudo systemctl disable --now gotouhou-agent-watchdog.timer
sudo systemctl enable --now gotouhou-goal-agent-manager.timer
sudo systemctl enable --now gotouhou-hourly-progress.timer
```

Example `/etc/gotouhou/progress-mail.env`:

```sh
GOTOUHOU_SMTP_HOST=smtp.ym.163.com
GOTOUHOU_SMTP_PORT=25
GOTOUHOU_SMTP_USER=example@ym.163.com
GOTOUHOU_SMTP_PASSWORD=replace-with-mail-authorization-code
GOTOUHOU_MAIL_FROM=example@ym.163.com
GOTOUHOU_MAIL_TO=wjcwqc@qq.com
```

Use `GOTOUHOU_SMTP_STARTTLS=1` only if the target SMTP account supports STARTTLS
on the configured port.

Operational status files:

- `/root/gotouhou/.agents/goal-agent-summary.json`: current goal agent status;
- `/root/gotouhou/.agents/goal-agent-supervisor-last-run.json`: latest
  15-minute supervisor JSON output;
- `/root/gotouhou/.agents/goal-agent-supervisor-last-error.log`: last
  15-minute supervisor stderr or lock-busy note;
- `/root/gotouhou/.agents/hourly-snapshots/*.json`: periodic samples;
- `/root/gotouhou/.agents/last-watchdog-summary.json`: latest mail summary input, kept for mail compatibility;
- `/root/gotouhou/.agents/goal-agent-manager-last-error.log`: last manager stderr when the runner had to send a failure mail;
- `/root/gotouhou/.agents/checks/latest-regression.json`: latest Godot, protocol, and Docker/docker-compose regression result;
- `/root/gotouhou/.agents/reports/audit-agent-latest.md`: Chinese audit report used by mail;
- `/root/gotouhou/.agents/reports/plan-audit-latest.md`: compatibility copy of the audit report;
- `/root/gotouhou/.agents/personas/`: persistent agent persona documents;
- `/root/gotouhou/.agents/agent-prompts/`: current persistent goal-agent prompts;
- `/root/gotouhou/.agents/worktrees/`: independent agent worktrees;
- `/root/gotouhou/.agents/logs/`: fallback `codex exec` logs;
- `/root/gotouhou/.agents/locks/`: per-agent and per-repository lock files.

Validate units after installing:

```sh
systemd-analyze verify /etc/systemd/system/gotouhou-hourly-progress.service /etc/systemd/system/gotouhou-hourly-progress.timer
systemd-analyze verify /etc/systemd/system/gotouhou-goal-agent-manager.service /etc/systemd/system/gotouhou-goal-agent-manager.timer
```

## GitHub branch protection

`configure_github_protection.py` configures the public repositories with:

- required protocol-audit checks on `main`;
- code-owner review metadata for pull requests;
- stale review dismissal;
- conversation resolution;
- force-push and branch-deletion denial;
- delete branch on merge.

Run after authenticating `gh` with repository administration permissions:

```sh
python3 ops/configure_github_protection.py
```

GitHub auto-merge is PR-scoped and must still be enabled on eligible pull
requests after required checks pass. The repository-level script creates the
required merge gate that auto-merge depends on.

The Phantasm-Klash organization currently has a single visible member, so the
script sets the required approving review count to `0` to avoid self-review
deadlock while still preserving required checks and CODEOWNERS metadata. When a
separate reviewer or team exists, raise the count to `1`.

## Cross-repository protocol audit

`protocol_audit_check.py` runs the protocol checker, Go runtime contract tests,
Battle Server checker, and a direct cross-repository compatibility pass across
`PhK-Protocol`, `SpellKard`, `Gensoulkyo`, and `PhK-BattleServer`.

```sh
python3 ops/protocol_audit_check.py
```

The direct pass verifies generated protocol versions and required message
fields, shared battle-result, mode-action, battle-snapshot, and battle-event
fixtures, SpellKard descriptor and mode-action client builder authority guards,
Gensoulkyo local protocol wiring, and Battle Server manifest/version/mode-action
boundaries. It also audits the golden replay summary fixture through
PhK-Protocol Go/C++ manifests into Gensoulkyo protocol/service tests and
PhK-BattleServer tests for replay id, match id, owner user id, input/event
counts, input/event stream hashes, final state hash, and final tick.
Snapshot/event and golden replay summary fixture coverage is expected to fail
until the corresponding PhK-Protocol manifest constants and downstream tests
have landed in the sibling repositories. It is safe to run on a development
host with the sibling repositories checked out under `/root/gotouhou`.
