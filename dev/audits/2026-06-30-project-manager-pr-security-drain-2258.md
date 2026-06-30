# project-manager PR security drain 2258

Time: 2026-06-30T22:58:19Z

## Scope

- Read `docs/dev/progress.md`, `docs/dev/gotouhou`, `docs/ops/README.md`, and `docs/ops/goal_agent_manager.py`.
- Limited work to PR review, protocol/security gate evidence, version-flow routing, and manager audit notes.
- No client, battle-server, or Nakama business implementation was changed.

## Closed Loop

- Gensoulkyo PR #55 `test: pin Nakama service callback docs contract` was diff-reviewed and merged at `6990adbf872ebb77e8dbf3bc4b823c3e85b358d2`.
- PhK-BattleServer PR #59 `Reject unsafe transfer card audit ids` was not merged; the PR now has a blocking manager comment because its new audit-token allowlist still accepts backslash.
- Gensoulkyo legacy root checkout `agent/gensoulkyo-lobby/20260629-0900` remains dirty with four Nakama binding files, but #55 already records this work as superseded by the main managed implementation; do not expand that legacy branch.

## Verification

- `go test ./runtime/... ./cmd/gensoulkyo_nakama` on PR #55 worktree: PASS.
- `python3 docs/ops/protocol_audit_check.py --root /tmp/gotouhou-pr55-root` with PR #55 as `Gensoulkyo`: PASS.
- GitHub #55 checks `server-contract-tests` and `auto-merge`: PASS before merge.
- `docker-compose --profile test run --rm test` on PR #55 worktree: FAILED in dependency download, first error `proxy.golang.org ... i/o timeout`; no test assertion failed.

## Next Routing

- `battle-server-agent`: update #59 by removing backslash from the transfer card audit id allowlist and adding a rejecting test, then rerun `docker-compose run --rm test` and protocol audit.
- `nakama-server-agent`: continue from latest `origin/main`; treat legacy `agent/gensoulkyo-lobby/20260629-0900` dirty files as superseded unless a fresh diff shows unique value.
- `project-manager-agent`: run normal manager resampling after this commit so merged #55 and blocked #59 are reflected in queue actions.
