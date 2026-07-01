# 2026-07-01 project-manager PR46/Gensoulkyo disposition

- Closed SpellKard #46 after diff review: replay local-load requests stay local-practice/hash scoped, server-audit or server-claim records are blocked before file load, and client-authored settlement/reward/damage authority stays false.
- Closed PhK-BattleServer #62 after diff review: Boss-mode bullet spawns now wait for the ready/start boundary; `python3 tools/check_battle_server.py`, `docker-compose run --rm test`, and protocol audit passed.
- Verified protocol/security gate with `python3 /root/gotouhou/docs/ops/protocol_audit_check.py`: pass across PhK-Protocol, Gensoulkyo, and PhK-BattleServer.
- Gensoulkyo root checkout dirty=4 on `agent/gensoulkyo-lobby/20260629-0900` was reviewed as legacy/superseded: managed branch/main already carry the stricter PR #59 implementation using `core.ServiceCallbackContext()`, allowlisted callback ops, and accepted callback values; do not migrate this root dirty diff.
- Remaining gates: Gensoulkyo #60 is documentation/status-only and still BLOCKED by branch protection/review; docs #72 carries this compact manager disposition note.
