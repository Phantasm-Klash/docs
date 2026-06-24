# Phantasm Klash Development Progress

Status date: 2026-06-25

## Current Phase

Phase 0: public repository initialization and first client prototype.

## Repository Status

| Repository | Status | Notes |
| --- | --- | --- |
| docs | Started | Public project docs, licensing notes, website stub, and development progress are present. |
| Gensoulkyo | Started | Server repository shell is initialized; runtime implementation is pending. |
| SpellKard | Started | Godot project skeleton and first local STG prototype are present. |

## Client Progress

SpellKard now includes a minimal Godot 4 prototype with:

- movement by arrow keys or WASD;
- focus speed by Shift;
- visible hitbox while focused;
- simple radial bullet spawner;
- graze counter;
- hit counter;
- debug HUD.

## Next Steps

1. Validate SpellKard in Godot 4.x and adjust any project file syntax issues.
2. Add local replay input recording and playback.
3. Draft Gensoulkyo contracts for login, room creation, tick input, snapshots, and replay metadata.
4. Add a license manifest template for assets.
5. Replace placeholder website visuals only after licensed media exists.
