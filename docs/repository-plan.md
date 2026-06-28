# Repository Plan

The project is initialized as three public repositories.

## Phantasm-Klash

Umbrella repository for:

- public introduction;
- documentation index;
- development process;
- development progress;
- open-source boundary;
- promotional website;
- shared license policy.

## Gensoulkyo

Server repository for:

- Nakama/Go business runtime;
- lobby, room, matchmaking, and session services;
- inventory, decks, chests, rewards, activity, leaderboard, and battle ticket services;
- database migrations;
- battle result verification plus replay and audit metadata;
- self-hosted deployment notes.

Current implementation contains a Go HTTP MVP with in-memory authority for sessions, inventory, decks, card upgrades, chests, matchmaking, room codes, match input, snapshots, events, reconnect, settlement, rematch, replay audit, rewards, activity, battle server allocation/tickets, and mode slices. PostgreSQL migrations, Nakama business RPC/WSS binding, production C++ Battle Server integration, production deployment, and full shared rule extraction are still pending. Nakama remains the business server core; Go match simulation is a contract/fallback path, not the long-term production high-frequency battle runtime.

## PhK-Protocol

Local shared protocol directory for:

- protobuf schemas;
- business secure envelope definitions;
- battle ticket structures;
- ruleset schemas;
- generated Go/C++/client bindings;
- compatibility fixtures and golden replay inputs;
- fixed-point battle units, 60Hz v0.1 tick contract, canonical state hash, and battle result signature contracts.

This repository should be open source and versioned before production C++ Battle Server migration begins. Draft schemas and manifest/descriptor bridges already exist; full generated Go/C++/Godot protobuf bindings are still pending.

Current repository boundary: `/root/gotouhou/PhK-Protocol` is now a local `main` Git working tree with initial commit `73901c3`. The public GitHub repository `https://github.com/Phantasm-Klash/PhK-Protocol` exists, but it is still empty until the initial `main` push succeeds. The next infrastructure step is to push `main`, then enable the same protocol-audit branch protection used by `Gensoulkyo` and `SpellKard`.

## PhK-BattleServer

Local C++ combat server directory for:

- ECDHE + KCP/UDP + protobuf + ChaCha20-Poly1305 battle transport;
- authoritative 60Hz PVP, battle royale, world Boss, and instance Boss tick simulation;
- snapshot, event, reconnect, replay-stream, and signed battle result generation;
- performance and latency tests.

This repository should be open source for the base combat rules. It must not contain Steam SDK files, commercial drop strategies, or official private deployment secrets. Current implementation is a C++ skeleton with packet/ticket/result structural guards plus an early 60Hz authoritative simulation/hash snapshot slice; real KCP, crypto, protobuf bindings, and golden replay validation are still pending.

Current repository boundary: `/root/gotouhou/PhK-BattleServer` is now a local `main` Git working tree with initial commit `7f93f5b`. The public GitHub repository `https://github.com/Phantasm-Klash/PhK-BattleServer` exists, but it is still empty until the initial `main` push succeeds. The next infrastructure step is to push `main`, then require C++ checker/build jobs before merging network or simulation PRs.

## SpellKard

Client repository for:

- Godot project files;
- STG movement and presentation;
- card UI and deck building;
- replay playback;
- theme and asset pipeline;
- local tools and tests.

Current implementation contains a Godot 4.7 local STG prototype with bullet math/pattern bases, practice stages, Pattern Lab, characters, cards/decks/chests, replay, UI row models, i18n/theme/accessibility/input/audio settings, Gensoulkyo HTTP contract projection, and headless validation tools. Final visual scenes, production assets, and polished online UX are still pending.

`SpellKard` now includes a GitHub protocol-audit workflow, CODEOWNERS, PR checklist, and `tools/ci_static_checks.py` for JSON, i18n, asset manifest, and network/protocol client script checks. Godot headless jobs should be added once a Linux Godot binary is available in CI.

## Closed Private Repositories

Private repositories are planned for:

- `PhK-SteamAdapter`: Steamworks SDK, Steam auth, ownership verification, Steam Inventory, Workshop, achievements, and market integration.
- `PhK-CommerceOps`: official products, cosmetic/item sale configuration, commercial inventory mapping, drop rates, fraud controls, ban linkage, and sensitive operations configuration.
- `PhK-OfficialDeploy`: official certificates, keys, infrastructure, observability, and production deployment policies.

The open-source release should remain self-hostable without these private repositories.
