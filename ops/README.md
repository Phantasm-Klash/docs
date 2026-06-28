# gotouhou Ops Helpers

## Hourly progress mail

`hourly_progress_mail.py` sends a multi-repository summary to `wjcwqc@qq.com`
through `smtp.ym.163.com:25`. It reads SMTP credentials from environment
variables and does not store secrets in git.

Dry run:

```sh
python3 ops/hourly_progress_mail.py --dry-run
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
fields, shared battle-result and mode-action fixtures, SpellKard descriptor and
mode-action client builder authority guards, Gensoulkyo local protocol wiring,
and Battle Server manifest/version/mode-action boundaries. It is safe to run on
a development host with the sibling repositories checked out under
`/root/gotouhou`.
