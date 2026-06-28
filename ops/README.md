# gotouhou Ops Helpers

## Hourly progress mail and watchdog

`agent_watchdog.py` runs before the hourly mailer. It samples the manager,
the four development scopes, two continuous review scopes, the five child
repositories, and systemd mail status. If a scope is missing it starts a
fallback `codex exec` worker.
If a scope has no commit, scoped diff, heartbeat, or log progress for two
consecutive hourly samples, it starts a replacement worker. The watchdog writes
host-local state under `/root/gotouhou/.agents/` and does not store secrets in
git.

Fallback workers are launched with Codex `/goal` sustained-target prompts. The
watchdog reads per-agent API keys from the host-local `/root/.codex/keys` file
or from `CODEX_AGENT_KEYS` when set. The file may contain `alias: value` or
`alias=value` lines; key values are injected into child process environment only
and are never written to JSON, logs, email, or git. Current default alias
fallbacks are:

- `spellkard-bullet`, `spellkard-ui`: `spellkard`;
- `gensoulkyo-lobby`: `gensoulkyo`;
- `phk-battle-server`, `change-describer`, `plan-auditor`, `manager`: `other`.

Keep `/root/.codex/keys` mode `0600`; the hourly email reports only aliases and
permission warnings.

Development workers use feature branches and pull requests by default:

- create a scoped branch from latest `origin/main`, for example
  `agent/<scope>/<YYYYMMDD-HHMM>`;
- commit each verified stage separately;
- push the branch and open a PR with summary, tests, risks, protocol/network/security impact, and docs/dev direction notes;
- avoid direct `main` pushes unless the manager explicitly declares an emergency hotfix.

The watchdog samples open PRs across the five repositories. When explicitly
enabled with `GOTOUHOU_WATCHDOG_APPROVE_PRS=1` or `--approve-prs`, it may read
PR metadata, check docs/dev direction, run local gates, and approve non-draft
`main` PRs without blockers via `gh pr review --approve`. It does not merge PRs.

SpellKard workers should use the Linux Godot binary at
`/root/gotouhou/Godot_v4.7-stable_linux.x86_64` for headless checks. Server
workers should prefer Docker regression through `docker-compose`; if a server
repo has no Dockerfile/compose files, the worker must run local regression and
record the Docker gap in the report.
Pure Godot renderer failures caused by a headless server without a GPU may be
marked ignored/blocked. GDScript parse, compile, type, script-load, UI contract,
or bullet contract failures are real regressions and must not be ignored.

`hourly_progress_mail.py` sends a concise watchdog-aware summary to
`wjcwqc@qq.com` through `smtp.ym.163.com:25`. It reads SMTP credentials from
environment variables and does not print or store the password.

Dry run:

```sh
python3 ops/agent_watchdog.py --dry-run
python3 ops/hourly_progress_mail.py --dry-run
```

Legacy full git report:

```sh
python3 ops/hourly_progress_mail.py --dry-run --full
```

Systemd setup on the development host:

```sh
sudo install -d -m 0750 /etc/gotouhou
sudo install -m 0755 ops/hourly_progress_runner.sh /root/gotouhou/docs/ops/
sudo install -m 0644 ops/gotouhou-hourly-progress.service /etc/systemd/system/
sudo install -m 0644 ops/gotouhou-hourly-progress.timer /etc/systemd/system/
sudo editor /etc/gotouhou/progress-mail.env
sudo systemctl daemon-reload
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

- `/root/gotouhou/.agents/agent-roster.json`: scope roster and fallback starts;
- `/root/gotouhou/.agents/hourly-snapshots/*.json`: hourly samples;
- `/root/gotouhou/.agents/last-watchdog-summary.json`: latest mail summary input;
- `/root/gotouhou/.agents/watchdog-last-error.log`: last watchdog stderr when the runner had to send a failure mail;
- `/root/gotouhou/.agents/checks/latest-regression.json`: latest Godot, protocol, and Docker/docker-compose regression result;
- `/root/gotouhou/.agents/reports/change-summary-latest.md`: Chinese feature summary for email;
- `/root/gotouhou/.agents/reports/plan-audit-latest.md`: docs/dev direction audit and prompt suggestions;
- `/root/gotouhou/.agents/agent-prompts/`: current persistent review-agent prompts;
- `/root/gotouhou/.agents/logs/`: fallback `codex exec` logs;
- `/root/gotouhou/.agents/locks/`: per-scope and per-repository lock files.

Validate units after installing:

```sh
systemd-analyze verify /etc/systemd/system/gotouhou-hourly-progress.service /etc/systemd/system/gotouhou-hourly-progress.timer
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
