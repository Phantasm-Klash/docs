# 数据库结构

## cards

```sql
create table cards (
  id uuid primary key,
  code text unique not null,
  i18n_key text not null,
  rarity text not null,
  card_type text not null,
  target_type text not null,
  cost int not null,
  duration_ticks int not null,
  cooldown_ticks int not null,
  effect_json jsonb not null,
  tags text[] not null default '{}',
  season_id text,
  enabled boolean not null default true
);
```

## player_wallets

```sql
create table player_wallets (
  user_id uuid primary key,
  points bigint not null default 0,
  card_dust bigint not null default 0,
  chest_keys bigint not null default 0,
  updated_at timestamptz not null
);
```

## player_card_inventory

```sql
create table player_card_inventory (
  user_id uuid not null,
  card_id uuid not null,
  copies int not null default 0,
  level int not null default 1,
  first_obtained_at timestamptz not null,
  primary key (user_id, card_id)
);
```

## player_decks

```sql
create table player_decks (
  id uuid primary key,
  user_id uuid not null,
  name text not null,
  format text not null,
  card_ids jsonb not null,
  active boolean not null default false,
  updated_at timestamptz not null
);
```

## chest_pools

```sql
create table chest_pools (
  id uuid primary key,
  season_id text not null,
  name text not null,
  cost_json jsonb not null,
  weights_json jsonb not null,
  pity_json jsonb not null,
  starts_at timestamptz not null,
  ends_at timestamptz,
  enabled boolean not null default true
);
```

## chest_openings

```sql
create table chest_openings (
  id uuid primary key,
  user_id uuid not null,
  pool_id uuid not null,
  server_seed text not null,
  result_json jsonb not null,
  cost_json jsonb not null,
  created_at timestamptz not null
);
```

## steam_item_links

Steam 商业版使用闭源迁移或私有表维护 Steam Inventory 物品映射。开源 schema 只保留可选扩展点：

```sql
create table external_item_links (
  id uuid primary key,
  user_id uuid not null,
  provider text not null,
  provider_item_id text not null,
  local_card_id uuid,
  payload_json jsonb not null,
  created_at timestamptz not null
);
```

## matches 与 match_players

```sql
create table matches (
  id uuid primary key,
  mode text not null,
  mode_ruleset_version text,
  ruleset_version text not null,
  server_seed text not null,
  status text not null,
  started_at timestamptz,
  ended_at timestamptz
);

create table match_players (
  match_id uuid not null,
  user_id uuid not null,
  side int not null,
  deck_snapshot_json jsonb not null,
  score bigint not null default 0,
  graze_count int not null default 0,
  hit_count int not null default 0,
  result text,
  reward_json jsonb,
  primary key (match_id, user_id)
);
```

## player_ratings

```sql
create table player_ratings (
  user_id uuid not null,
  season_id text not null,
  rating_code text not null,
  rank_score int not null default 0,
  certified_at timestamptz,
  next_unlock_eligible boolean not null default false,
  updated_at timestamptz not null,
  primary key (user_id, season_id, rating_code)
);
```

## rating_challenge_results

```sql
create table rating_challenge_results (
  id uuid primary key,
  user_id uuid not null,
  season_id text not null,
  rating_code text not null,
  stage_id text not null,
  passed boolean not null,
  result_json jsonb not null,
  replay_id uuid,
  created_at timestamptz not null
);
```

## boss_instances

```sql
create table boss_instances (
  id uuid primary key,
  boss_code text not null,
  mode text not null,
  season_id text,
  max_hp bigint not null,
  current_hp bigint not null,
  friendly_fire_mode text not null,
  starts_at timestamptz not null,
  ends_at timestamptz,
  defeated_at timestamptz
);
```

## boss_attempts

```sql
create table boss_attempts (
  id uuid primary key,
  boss_instance_id uuid not null,
  match_id uuid not null,
  user_id uuid not null,
  damage bigint not null default 0,
  survived boolean not null,
  clear_result text,
  reward_json jsonb,
  created_at timestamptz not null
);
```

## daily_attempt_limits

```sql
create table daily_attempt_limits (
  user_id uuid not null,
  mode text not null,
  date_key text not null,
  used_attempts int not null default 0,
  max_attempts int not null,
  updated_at timestamptz not null,
  primary key (user_id, mode, date_key)
);
```

## battle_royale_matches

```sql
create table battle_royale_matches (
  match_id uuid primary key,
  public_pool_json jsonb not null,
  zero_round_order_json jsonb not null,
  round_events_json jsonb not null default '[]'::jsonb
);
```

## match_events

```sql
create table match_events (
  id bigserial primary key,
  match_id uuid not null,
  tick int not null,
  event_type text not null,
  payload_json jsonb not null
);
```

## rooms 与 battle ticket 审计

当前 Go Runtime 的 Nakama 大厅 MVP 先以内存状态实现 `rooms.create/list/get/rules/join/leave`、match allocation 和 battle ticket 申请。PostgreSQL 持久化阶段需要补齐房间和 ticket 审计表，至少保存：

- `room_code`、`host_user_id`、`mode`、`status`、`stage_id`、`mode_params_json`、`created_at`、`matched_at`、`closed_at`。
- room participant 的 `ticket_id`、`user_id`、`deck_snapshot_hash`、`loadout_json`、`joined_at`、`left_at`、`status`。
- battle allocation 的 `match_id`、`battle_server_id`、`endpoint`、`mode_config_hash`、`allocated_at`。
- battle ticket 的 `ticket_id`、`match_id`、`user_id`、`battle_server_id`、`deck_snapshot_hash`、`issued_at`、`expires_at`、`revoked_at` 和签名 key id。

这些表只作为业务大厅、审计和重连恢复数据源；权威战斗状态、分数、伤害、擦弹、命中、Boss HP 和奖励仍由服务端结算链路写入 `matches`、`match_players`、`match_events` 与奖励流水。
