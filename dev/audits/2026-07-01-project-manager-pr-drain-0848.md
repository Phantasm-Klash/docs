# 2026-07-01 Project Manager PR Drain

## Closed loops

- SpellKard #71 was diff-reviewed and merged after `python3 tools/ci_static_checks.py` and `python3 /root/gotouhou/docs/ops/protocol_audit_check.py` passed; root `SpellKard` was fast-forwarded to `origin/main`.
- Gensoulkyo #93 was diff-reviewed and found already merged at `b24a4e72d0bb80da5fa2c600e38df6b262df8ef8`; `go test ./runtime/... ./cmd/gensoulkyo_nakama`, `docker-compose --profile test run --rm test`, and protocol audit passed; root `Gensoulkyo` was fast-forwarded.
- PhK-BattleServer #91 was diff-reviewed and merged after `python3 tools/check_battle_server.py`, `docker-compose run --rm test`, and protocol audit passed; root `PhK-BattleServer` was fast-forwarded to `origin/main`.
- Normal manager resampling refreshed the PR queue to `open=0`; docs worktrees are clean and not ahead.

## Remaining routing

- `client-agent` is now the top version-flow risk with dirty work in `godot/scripts/game_mode_model.gd` and `tools/client_smoke_test.gd`; require scoped checks, commit, push, and PR or a clear discard rationale.
- `audit-agent`, `battle-server-agent`, and `client-agent` still have medium resource pressure; next prompts should stay structured and short.
