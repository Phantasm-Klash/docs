# Open Source Boundary

Phantasm Klash uses an open-source core model.

## Public Repositories May Include

- client gameplay code;
- Nakama/Go business server code for lobby, room, matchmaking, account, inventory, decks, rewards, activity, leaderboard, and battle ticket services;
- C++ Battle Server code for base PVP/Boss combat simulation;
- shared protobuf, ruleset schema, business envelope, battle ticket, and codegen definitions;
- non-platform-specific account flows;
- self-hosted database schemas;
- replay, practice, spectate, and test tooling;
- original project text and code;
- assets with explicit open licenses and recorded provenance.

## Public Repositories Must Not Include

- platform SDK files that cannot be redistributed;
- commercial service secrets;
- private API keys;
- unreleased commercial economy parameters;
- official product, cosmetic, commercial inventory, or sale configuration;
- moderation or fraud-control secrets;
- unlicensed third-party media;
- copyrighted game assets from unrelated projects.

## Adapter Boundary

Commercial platform adapters should integrate through documented interfaces. The open-source core must remain runnable without those adapters.

Nakama/Go remains the open-source business server core. The C++ Battle Server is open for base combat rules and performance work. Steam ownership, Steam Inventory, market integration, official product configuration, drop strategy, fraud controls, private certificates, and official deployment secrets stay in private repositories.
