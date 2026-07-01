# Project manager resample 2026-07-01 11:32 UTC

- Re-sample: live GitHub open PRs are Gensoulkyo #102 only; PhK-BattleServer #102-#104 are merged, and all repository open-PR counts except Gensoulkyo are 0.
- Version state: audit-agent docs root is now clean on `main`; project-manager branch is clean before this report; the previous summary entry for docs dirty/legacy is stale until the next normal manager sample.
- Priority routing: client-agent still owns SpellKard dirty work (`godot/i18n/base.*.json`, `godot/scripts/stage_select_model.gd`, `tools/client_smoke_test.gd`) and must preserve/supersede it before syncing the checkout.
- PR routing: nakama-server-agent must review/merge or explain Gensoulkyo #102 after checks; its current head is clean and remote-tracking.
- Regression: latest stored regression remains failed on Godot headless `client_ui_smoke_test.gd` status 124 with no first error captured; keep client reports compressed to command, result, first key error, and next action.
