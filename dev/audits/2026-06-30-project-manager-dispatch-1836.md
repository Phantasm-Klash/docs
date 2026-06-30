# project-manager-agent dispatch snapshot 2026-06-30T18:39Z

## Context

- `docs/dev/progress.md` still puts the project on Phase 3: server-authoritative online MVP and server split convergence.
- Open PR queue is empty across docs, SpellKard, Gensoulkyo, PhK-BattleServer, and PhK-Protocol after merging Gensoulkyo #42 and SpellKard #28.
- A normal manager sample was run after the merges to refresh `goal-agent-summary.json`, `last-watchdog-summary.json`, prompts, and mail inputs.

## Current routing

| Agent | Repo | State | Required next action |
| --- | --- | --- | --- |
| client-agent | SpellKard | running; managed branch `agent/client-agent/boss-result-authority` clean at `567251e`; PR #28 merged | Keep reports short because client log risk is high. Next client baseline hygiene is syncing root `main`, which is behind `origin/main` by 1. |
| nakama-server-agent | Gensoulkyo | running; managed branch `agent/nakama-server-agent/final-20260630` clean at `00bfa2b`; PR #42 merged | Resolve the legacy root checkout dirty=4 by migrating useful service-origin gate work or documenting it as superseded. Keep reports compressed. |
| battle-server-agent | PhK-BattleServer | running; managed branch `agent/battle-server-agent/current-20260630-1824` ahead=1 at `3da6d3a`; root checkout still legacy branch | Push the ahead commit and open/update a PR, or write a blocker. Do not use the root legacy branch as baseline. |
| audit-agent | docs | running; root docs clean | Audit only structured status, PR state, check results, and key errors. Do not paste long logs. |
| project-manager-agent | docs | running; persistent branch clean before this snapshot | Keep closing dirty/ahead/PR loops before assigning new feature slices. |

## Risk notes

- `SpellKard` root `main` is behind `origin/main` by 1; this is a baseline hygiene item for client-agent after the dirty managed branch is submitted.
- `Gensoulkyo` root checkout remains on legacy `agent/gensoulkyo-lobby/20260629-0900` with four dirty files under `cmd/gensoulkyo_nakama`.
- `PhK-BattleServer` managed branch is now the highest priority version-flow item because it is ahead=1 and needs push/PR or a clear blocker.
- Resource pressure remains high for client-agent and project-manager-agent, medium for audit-agent, battle-server-agent, and nakama-server-agent; all agents should summarize checks and PR state only.

## Checks sampled

- Latest regression summary: ok=true, failed=0, generated at 2026-06-30T18:00:44Z.
- Manager sample: `python3 docs/ops/goal_agent_manager.py --root /root/gotouhou` completed with failures=[], open PR=0, health score=82, started_count=1.
- Merged PRs reviewed in this manager pass: Gensoulkyo #42 (`Pin service callback context contract`) and SpellKard #28 (`Expose boss result rejection reason`).
