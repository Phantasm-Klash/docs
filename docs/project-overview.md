# Project Overview

Phantasm Klash 幻想交锋 is a networked bullet-hell card battle project.

The core fantasy is a duel where movement skill, pattern reading, deck construction, and timing all matter. Players dodge dense patterns, graze for value, trigger card effects, and compete in server-authoritative matches that can be replayed and audited.

## Components

### Gensoulkyo

Gensoulkyo is the server-side project. It is responsible for:

- account and session services;
- lobby and matchmaking flows;
- authoritative match simulation;
- persistence for player state, decks, inventory, rewards, and leaderboards;
- replay metadata and match audit data;
- open-source self-hosted server operation.

### SpellKard

SpellKard is the client-side project. It is responsible for:

- Godot-based bullet-hell client development;
- input, movement, hitbox, graze, bomb, and replay presentation;
- card UI and deck editing;
- local practice and debug tooling;
- theme and asset loading;
- accessibility, localization, audio, and controller support.

## Name Usage

The formal project name is `Phantasm Klash 幻想交锋`.

Accepted abbreviations:

- `PhK`
- `P.K.`

Repository names:

- `docs`
- `Gensoulkyo`
- `SpellKard`

