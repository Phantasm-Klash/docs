# project-manager PR head verification 2026-07-01T10:08Z

- Closed loop: docs #80 is merged; do not use the docs root checkout legacy branch `agent/audit-agent/status-20260701-0951` as a baseline.
- Verified PR heads: PhK-BattleServer #95 passed `python3 tools/check_battle_server.py`, `docker-compose run --rm test`, and `python3 /root/gotouhou/docs/ops/protocol_audit_check.py` in a detached PR-head worktree; Gensoulkyo #97 passed `go test ./runtime/... ./cmd/gensoulkyo_nakama`, `docker-compose --profile test config`, and protocol audit in a detached PR-head worktree.
- Hold merge for #95/#97 until owning managed worktrees finish their current dirty slices on the same branches, to avoid deleting or invalidating active agent branch tracking while uncommitted follow-up work exists.
- Next actions: battle-server-agent and nakama-server-agent must commit/push or explicitly abandon their dirty follow-up work before merge; client-agent/SpellKard #75 remains next protocol-sensitive PR review; all medium-risk agents must keep reports to structured status, failed command, first key error, and next action.
