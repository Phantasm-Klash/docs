# 2026-07-01 project-manager PR drain snapshot

## Closed loop

- PhK-BattleServer #106 `Clamp Boss room capacity to protocol range` reviewed as a protocol/network boundary change and merged after local gates passed.
- Local gates for #106: `python3 tools/check_battle_server.py`, `docker-compose run --rm test`, and `python3 /root/gotouhou/docs/ops/protocol_audit_check.py`.
- Main sync: `/root/gotouhou/PhK-BattleServer` fast-forwarded to `c596577`.

## Blocked merge

- SpellKard #79 is GitHub-clean, but local full client gate is not clean.
- Passing checks on PR head `33253da`: `python3 tools/ci_static_checks.py`, `client_smoke_test.gd`, and `boss_pattern_catalog_check.gd`.
- Failing check: `client_ui_smoke_test.gd` fails with `snapshot:modes: timed out after 45000 ms at frame 75`.
- Action: #79 received a manager review comment and must fix the modes snapshot timeout before merge.

## Next routing

- `client-agent`: stop expanding stage content; fix #79 `snapshot:modes` UI smoke timeout, then rerun the four client gates.
- `nakama-server-agent`: stop new slices until Gensoulkyo main dirty `runtime/httpapi/handler_test.go` is preserved, superseded, or discarded explicitly.
- `audit-agent` / `project-manager-agent`: docs main ahead state still needs push/PR or explicit supersede decision.
