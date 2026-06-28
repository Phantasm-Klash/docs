# Protocol Audit Process

Network, protocol, battle-ticket, replay, room, matchmaking, and settlement
changes must pass an explicit compatibility and security audit before merge.

## Required checks

- `PhK-Protocol`: schema, descriptor, ruleset, and manifest checks.
- `Gensoulkyo`: Go runtime tests for Nakama/HTTP business contracts.
- `PhK-BattleServer`: C++ battle server contract checks.
- `SpellKard`: Godot headless/client contract checks when client packet or UI
  connection behavior changes.

Run the local cross-repository check from the docs repository:

```sh
python3 ops/protocol_audit_check.py
```

## Review checklist

- The client still submits only input intent, deck/mode requests, and transport
  metadata, never authoritative score, hit, graze, reward, or result state.
- Battle tickets remain short-lived, mode-bound, player-bound, and signed by
  the business server.
- Replay, snapshot, result, and canonical hash fields are versioned.
- Nonces, sequence numbers, timestamps, and idempotency keys are validated on
  authenticated business routes.
- Battle Server changes do not grant inventory, rewards, Steam items, or direct
  database writes.
- New protocol fields are reflected in docs and generated manifests.

## PR automation target

The docs repository contains `.github/workflows/protocol-audit.yml` as the
canonical workflow template. Mirror it into each implementation repository, or
wire equivalent repository-specific checks, before enabling required branch
protection on `main`.
