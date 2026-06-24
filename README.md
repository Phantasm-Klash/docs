# Phantasm Klash 幻想交锋

Phantasm Klash, abbreviated as PhK or P.K., is an open-source networked bullet-hell card battle project. It combines precise STG movement, graze timing, replayable match simulation, and deck-driven PvP decisions.

This repository is the public documentation project for the Phantasm-Klash GitHub organization.

Runnable open-source components are split into:

- `Gensoulkyo`: authoritative server, lobby, match, account, inventory, and persistence services.
- `SpellKard`: Godot client, local bullet-hell prototype, UI, input, replay, and theme pipeline.

## Repository Role

This repository contains:

- product introduction and public-facing docs;
- development process and progress tracking;
- open-source and commercial boundary notes;
- promotional website source;
- shared licensing policy for code, documentation, and media.

## Project Principles

- The server is authoritative for online matches.
- The client is responsible for input, presentation, accessibility, and local practice tooling.
- Gameplay logic should be reproducible from versioned rules, deterministic seeds, deck snapshots, and input streams.
- Open-source repositories must not include platform secrets, commercial service keys, closed distribution adapters, or unlicensed third-party content.
- Public assets must have recorded provenance and license metadata before they enter the repositories.

## Development Notes

Development progress is tracked in [dev/progress.md](dev/progress.md).

The `dev/gotouhou/` folder contains early planning material under the original internal codename. It is kept as historical planning context only; formal project names are Phantasm Klash, Gensoulkyo, and SpellKard.

## Licensing

Unless otherwise noted:

- Source code is licensed under the MIT License.
- Documentation, website copy, and original non-code project text are licensed under CC BY 4.0.
- Visual, audio, font, and third-party assets require per-file license records before inclusion.

See [LICENSE](LICENSE), [LICENSE-CC-BY-4.0.md](LICENSE-CC-BY-4.0.md), and [docs/licensing.md](docs/licensing.md).

