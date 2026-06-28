# gotouhou Ops Helpers

## Hourly progress mail and watchdog

`agent_watchdog.py` runs before the hourly mailer. It samples the manager,
the four active development scopes, the five child repositories, and systemd
mail status. If a scope is missing it starts a fallback `codex exec` worker.
If a scope has no commit, scoped diff, heartbeat, or log progress for two
consecutive hourly samples, it starts a replacement worker. The watchdog writes
host-local state under `/root/gotouhou/.agents/` and does not store secrets in
git.

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
