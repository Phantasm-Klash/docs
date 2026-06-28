# Protocol Audit Process

Network, protocol, battle-ticket, replay, room, matchmaking, and settlement
changes must pass an explicit compatibility and security audit before merge.

## Required checks

- `PhK-Protocol`: schema, descriptor, ruleset, and manifest checks.
- `Gensoulkyo`: Go runtime tests for Nakama/HTTP business contracts.
- `PhK-BattleServer`: C++ battle server contract checks.
- `SpellKard`: Godot headless/client contract checks when client packet or UI
  connection behavior changes.

Run the local cross-repository check from the docs repository:

```sh
python3 ops/protocol_audit_check.py
```

The local audit now performs both per-repository checks and a cross-repository
contract check:

- `PhK-Protocol` descriptor, Go manifest, and C++ manifest versions must match.
- `PhK-Protocol` `battle_snapshot` and `battle_event` fixtures must be exported
  as shared Go/C++ manifest constants and consumed by Gensoulkyo and
  PhK-BattleServer tests.
- `PhK-Protocol` `golden_replay_summary` fixture values must be exported as
  shared Go/C++ manifest constants and consumed by Gensoulkyo protocol/service
  tests and PhK-BattleServer tests for `replay_id`, `match_id`,
  `owner_user_id`, `input_count`, `event_count`, `input_stream_hash`,
  `event_stream_hash`, `final_state_hash`, and `final_tick`.
- `SpellKard` must load the shared descriptor and validate the minimal battle
  packet/ticket/result contract.
- `SpellKard` mode-action client builders must submit only mode id, action
  type, copied payload intent, and `client_result_authoritative=false` through
  the Gensoulkyo mode-action endpoint; response handling may project server
  state into UI models but must keep server authority explicit.
- `Gensoulkyo` must depend on the local `PhK-Protocol` manifest and keep its
  protocol contract tests wired to shared version constants.
- `PhK-BattleServer` must consume the generated C++ manifest for version,
  ruleset, and required field gates.

## Review checklist

- The client still submits only input intent, deck/mode requests, and transport
  metadata, never authoritative score, hit, graze, reward, or result state.
- Battle tickets remain short-lived, mode-bound, player-bound, and signed by
  the business server.
- Replay, snapshot, result, and canonical hash fields are versioned.
- Nonces, sequence numbers, timestamps, and idempotency keys are validated on
  authenticated business routes.
- Battle Server changes do not grant inventory, rewards, Steam items, or direct
  database writes.
- New protocol fields are reflected in docs and generated manifests.

## PR automation target

The docs repository contains `.github/workflows/protocol-audit.yml` as the
canonical workflow template. Mirror it into each implementation repository, or
wire equivalent repository-specific checks, before enabling required branch
protection on `main`.

Current repository automation is managed by `ops/configure_github_protection.py`.
It configures required status checks, code-owner reviews, stale-review dismissal,
conversation resolution, branch deletion prevention, and delete-branch-on-merge
for `docs`, `SpellKard`, `Gensoulkyo`, `PhK-Protocol`, and `PhK-BattleServer`.
After a PR is opened, GitHub auto-merge can be enabled on that PR once the
required checks are present.

Operational progress mail is intentionally host-local. `ops/hourly_progress_mail.py`
can send an hourly multi-repository status summary when systemd timer units and
SMTP environment variables are installed on the development host, but SMTP
credentials are not part of the repository and the mailer is not a merge gate.

Because the organization currently has a single visible member, branch
protection keeps CODEOWNERS metadata but does not require a second approving
review. The effective merge gate is the required audit workflow plus optional
`codex-auto-merge` label for low-risk maintenance PRs.
