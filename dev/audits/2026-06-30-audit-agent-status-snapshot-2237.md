# audit-agent status snapshot 2237

Time: 2026-06-30T22:37Z

## Scope

- Direction checked: `docs/dev/progress.md`, `docs/dev/gotouhou`, and `docs/ops`.
- Current main line remains Phase 3 server-authoritative online MVP, with Phase 2/6/8 supporting client and mode work.
- This snapshot supersedes 22:35 because Gensoulkyo PR #54 auto-merged while the audit was closing.

## Current State

- `docs`: `main...origin/main`, clean after commit `832b813`.
- `SpellKard`: root `main...origin/main` behind=3; PR #40 merged at 2026-06-30T22:32:14Z; open PR none.
- `Gensoulkyo`: root on legacy `agent/gensoulkyo-lobby/20260629-0900`, dirty=4; PR #53 merged at 2026-06-30T22:30:56Z; PR #54 merged at 2026-06-30T22:34:53Z; open PR none.
- `PhK-BattleServer`: root `main...origin/main` ahead=2/behind=28; PR #58 merged at 2026-06-30T22:30:39Z; open PR none.
- `PhK-Protocol`: `main...origin/main`, clean; open PR none.

## Audit Conclusion

- Merged PRs #58/#54/#53/#40 remain aligned with docs/dev: they strengthen BattleServer replay/result hashing, Nakama business event contracts, and client replay authority presentation.
- Current open PR queue is empty; the next bottleneck is repository hygiene, not review queue size.
- Remaining version-flow risks are unchanged: Gensoulkyo legacy dirty work must be migrated or explicitly superseded, SpellKard root is behind, and PhK-BattleServer root main must not be used as a baseline until the local ahead/behind split is resolved.
- Old agent roster remains frozen; no old agent should be restarted except to migrate proven useful work into the five managed agents.

## Verification

- `python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py docs/ops/check_goal_agent_manager.py`: PASS.
- `python3 docs/ops/check_goal_agent_manager.py`: PASS.
- `python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou`: PASS.
