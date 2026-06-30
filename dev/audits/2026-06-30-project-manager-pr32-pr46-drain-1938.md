# project-manager-agent PR drain snapshot 2026-06-30T19:38Z

## Closed delivery loops

- Synced the project-manager managed docs worktree from `origin/main`; it is no longer behind by 2 commits.
- Diff-reviewed SpellKard PR #32 `Expose boss formation display summaries`.
  - Merge state before drain: clean, checks 2/0/0.
  - Merged at 2026-06-30T19:33:07Z with merge commit `736be5ad2c6e9278886fe0c54c0d64f0eda1ba4e`.
  - Security/authority review: the new Boss formation summary is `local_display_only`; damage, reward, settlement, and result authority remain server-owned.
- Diff-reviewed Gensoulkyo PR #46 `Expose activity business event contract`.
  - Merge state before drain: clean, checks 2/0/0.
  - Merged at 2026-06-30T19:32:53Z with merge commit `b604302b9a2c17c07f8b307ae22e0fda878623be`.
  - Security/authority review: the new activity business event is a read-only low-frequency WSS notification; `activity.claim` remains RPC-only and does not authorize battle tick or client result-submit paths.
- Ran a normal manager resample after the merges. The authoritative PR queue is now open=0, needs_action=0, ready=0.

## Checks

- `python3 /root/gotouhou/docs/ops/protocol_audit_check.py` passed.
- `python3 -m py_compile ops/goal_agent_manager.py ops/hourly_progress_mail.py ops/check_goal_agent_manager.py` passed.
- `python3 ops/check_goal_agent_manager.py` passed.
- `python3 ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start` passed.
- `python3 ops/hourly_progress_mail.py --dry-run --brief` passed.
- `python3 ops/goal_agent_manager.py --root /root/gotouhou` passed and refreshed `/root/gotouhou/.agents/goal-agent-summary.json`.

## Current forced next actions

- `nakama-server-agent`: score is now 66 (`needs_correction`). First stop and preserve or supersede dirty work in the managed worktree (`dirty=6`) and legacy root checkout (`dirty=4`) before expanding new server features.
- `battle-server-agent`: managed worktree has `dirty=3`; run the relevant battle checks, then commit and push/PR or write a blocker. Do not use the legacy root checkout as baseline.
- `client-agent`: managed worktree has `dirty=1` and root `SpellKard/main` is behind by 1; commit/PR the current replay slice, then sync root main. Keep reports short because resource risk is high.
- `audit-agent`: keep reports structured and short; current PR queue is empty, so next audit should focus on dirty/ahead/version-flow risk.
- `project-manager-agent`: resource risk remains high; continue closing dirty/ahead/PR loops and do not paste long logs.
