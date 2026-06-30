# project-manager dispatch 2240

Time: 2026-06-30T22:40:44Z

## Scope

- Read `docs/dev/progress.md`, `docs/dev/gotouhou`, `docs/ops/README.md`, and `docs/ops/goal_agent_manager.py`.
- Verified current repo/PR state for docs, SpellKard, Gensoulkyo, and PhK-BattleServer.
- Kept scope to scheduling, audit, and version flow; no client, battle-server, or Nakama business code was changed.

## Closed Loop

- Fast-forwarded project-manager managed docs worktree from `75fd11c` to `e17c1ed`, clearing the reported `behind=1`.
- Confirmed cross-repo open PR queue is empty after merged PRs `#58`, `#54`, `#53`, and `#40`.
- Refreshed normal manager sampling after the sync so stale PR/upstream-gone state is not carried forward.

## Verification

- `python3 -m py_compile ops/goal_agent_manager.py ops/hourly_progress_mail.py ops/check_goal_agent_manager.py`: PASS.
- `python3 ops/check_goal_agent_manager.py`: PASS.
- `python3 ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start`: PASS.
- `python3 ops/hourly_progress_mail.py --dry-run --brief`: PASS.

## Remaining Routing

- `nakama-server-agent`: stop on Gensoulkyo legacy dirty branch `agent/gensoulkyo-lobby/20260629-0900`; migrate useful Nakama SDK binding work or explicitly supersede it before new business slices.
- `battle-server-agent`: do not use PhK-BattleServer root `main` as a baseline until local `ahead=2/behind=28` is converted to a current-base branch or discarded by owner decision.
- `client-agent`: sync SpellKard root `main` behind=3 before treating it as a baseline.
- All running agents remain at medium resource risk; reports should stay compressed to structured status, failed commands, first key error, and next action.
