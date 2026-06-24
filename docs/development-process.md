# Development Process

## Workflow

1. Define behavior in docs before large implementation work.
2. Keep server and client contracts explicit.
3. Build a local client prototype before expanding online systems.
4. Add deterministic replay coverage for gameplay logic.
5. Record asset provenance before assets are committed.
6. Keep commercial platform adapters outside the open-source repositories unless explicitly approved for release.

## Branching

Initial development can happen on `main` until the first runnable prototype exists. After that:

- `main`: stable public state;
- `dev`: integration branch for active work;
- `feature/<area>-<name>`: scoped feature branches;
- `docs/<topic>`: documentation-only branches.

## Review Rules

Every feature should answer:

- What player-visible behavior changed?
- Does the server remain authoritative for online play?
- Can the behavior be replayed or audited?
- Are new assets licensed and recorded?
- Are secrets and closed platform dependencies excluded?

## Milestone Gates

- Documentation gate: scope, contracts, and licenses are written.
- Prototype gate: local SpellKard gameplay loop is playable.
- Online gate: Gensoulkyo can host a reproducible 1v1 match.
- Content gate: card rules, deck rules, and balance metrics are testable.
- Release gate: packaging, monitoring, and public instructions are complete.

