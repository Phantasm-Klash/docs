# Development Progress

Status date: 2026-06-28

## Current Phase

Main track: Phase 3, server-authoritative online MVP and server split convergence.

The initial repository/bootstrap phase is complete. SpellKard has moved from a minimal Godot movement demo into a local STG, practice, card/deck, replay, UI-model, and Gensoulkyo HTTP contract prototype. Gensoulkyo now contains an in-memory Go HTTP server MVP for the authority boundary. The next architecture keeps Nakama/Go as the business server core and adds a C++ Battle Server for high-frequency PVP/Boss combat over encrypted KCP/protobuf.

## Progress Table

| Area | Status | Notes |
| --- | --- | --- |
| Project naming | Done | Formal name: Phantasm Klash 幻想交锋. Abbreviations: PhK, P.K. |
| Repository split | Done | GitHub organization uses `docs`, `Gensoulkyo`, and `SpellKard`. |
| Public docs | Started | Overview, process, progress, licensing, open-source boundary, and gotouhou planning tree exist. Roadmap now reflects the real MVP state. |
| Promotional website | Stubbed | Static website structure exists; content is placeholder-level. |
| Gensoulkyo server | Started | Go HTTP MVP implements anonymous sessions, bootstrap, inventory/decks/chests, card upgrades, matchmaking, room codes, battle server allocation/tickets, battle result submit fallback, ready/input/snapshot/events, disconnect/reconnect, settlement, rematch, replay audit, activity claims, and mode authority slices in memory. `pvp_duel` is now exposed as a two-player mode with mode-bound battle tickets and a no-certification-mutation settlement guard. The planning tree now records the production battle sync route as server-authoritative 60Hz deterministic input sync with C++ simulation, canonical state hash, golden replay fixtures, and signed battle results, not P2P lockstep. PostgreSQL, Nakama business RPC/WSS, production C++ Battle Server integration, and deployment are pending. |
| SpellKard client | Started | Godot 4.7 prototype includes local STG play, 12 bullet pattern bases, practice stages, Pattern Lab, characters, cards/decks/chests, replay, mode/result surfaces, i18n/theme/accessibility/input/audio/display models, Gensoulkyo HTTP adapter with battle allocation/ticket/result-receipt projection, BattleNetworkClient prepare/connect/input-header scaffold actions for the KCP/protobuf/AEAD migration, runtime scene-backed shared UI hosts for home lobby, menu hub, community panel, player settings, matchmaking, playfield overlay, and collection pages, community/activity/friends/promotions surfaces, player settings deep links for gamepad movement curve/key binding/volume/resolution, settings snapshot summaries, selected-character gamepad move/focus speed-preview samples, page-spec-prioritized quick actions, player-facing page-experience summaries, and a `ClientMenuPageModel` + `page_layout()` contract that separates menu pages from practice and running battle displays while recording page density, primary/secondary rows, player task groups, setting groups, social groups, mode groups, scene ids, required bindings, and render slots for final scene migration. Page-specific final UI presentation, production assets, Nakama WSS, real KCP transport, and production AEAD are pending. |
| Asset manifest | Started | Machine-readable asset and base theme manifests exist. Production assets are still pending. |
| Tests | Started | Godot headless smoke, asset manifest, balance simulation, latency matrix, Gensoulkyo live HTTP check, Go unit/HTTP tests, and C++ battle server CTest checks exist. Client smoke now covers runtime scene-backed binding across all shared UI scene families, page task groups and page-experience summaries, settings snapshot summaries, selected-character gamepad move/focus speed previews, page-spec-prioritized quick actions, battle result submit/request receipt projection as non-authoritative UI state, and battle client handshake/connect/input-header scaffold actions. CI wiring is pending. |
| CI | Pending | Needs automated Go, Godot, manifest, docs, license, and deployment checks. |
| Public release | Pending | Requires persistent server storage, realtime transport, final UX pass, license audit, and repeatable self-hosted build instructions. |

## Next Milestones

1. Freeze v0.1 PhK-Protocol contracts for protobuf, business secure envelope, battle tickets, 60Hz battle tick, fixed-point units, canonical state hash, golden replay fixtures, rules/config, rewards, and replay metadata.
2. Keep Nakama/Go as the business server core and migrate login, session, inventory, decks, rooms, matchmaking, business WSS, battle ticketing, result verification, and persistence there.
3. Add PostgreSQL migrations and persistence for Gensoulkyo state currently held in memory.
4. Create the C++ Battle Server path for ECDHE + KCP/UDP + protobuf + ChaCha20-Poly1305 combat while preserving HTTP integration checks as contract tests.
5. Continue improving SpellKard's scene-backed UI hosts: the shared Home Lobby, Menu Hub, Community Panel, Settings Panel, Matchmaking Panel, Playfield Overlay, and Collection Panel now instantiate at runtime, while page-specific final composition, focus styling, controller/mouse ergonomics, and production-safe art/skin integration are still pending. Reuse the existing row/control metadata, `ClientMenuPageModel.page_spec()`, `page_layout()` policy, scene contracts, player task groups, page-experience summaries, PvP/Boss mode groups, Quick/Ranked/PvP/Boss/Room matching cards, social/promotion groups, and player-settings deep links for gamepad curve, key binding, volume, and resolution.
6. Establish multi-repo CI and remote Linux build/test automation for PhK-Protocol codegen, Go/Nakama, C++ battle, Godot headless checks, manifests, documentation, and license gates.
7. Expand content only after provenance is recorded: first production-safe UI skin, audio placeholders with licenses, and screenshots/concept art for the website.
