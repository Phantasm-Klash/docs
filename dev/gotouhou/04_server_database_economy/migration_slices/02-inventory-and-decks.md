# 02 库存与卡组迁移切片

状态：可实现规格，依赖 `01-login-and-bootstrap.md` 的 user/session 映射；
不包含代码。

## 范围

本切片把当前 Gensoulkyo 的玩家钱包、卡牌库存、卡组读取/保存和卡牌升级
迁移到 Nakama Runtime + storage：

- `inventory.get`（兼容 alias `inventory`）；
- `cards.upgrade`；
- `decks.list`；
- `decks.save`；
- bootstrap 中的 `wallet`、`inventory`、`decks` projection；
- 进入匹配前读取服务端 active deck snapshot 的前置数据。

不在范围内：

- 宝箱池、开箱、pity 和 `chest_openings`；
- match settlement、奖励流水、排行榜写入；
- 客户端本地卡牌 UI 或卡牌战斗效果；
- 战斗服 tick、卡牌施放和 battle result。

## 目标契约

### Nakama RPC

| RPC id | 输入 | 输出 payload | 幂等/并发 |
| --- | --- | --- | --- |
| `inventory.get` | 空对象 | `InventorySnapshot` | 只读 |
| `cards.upgrade` | `CardUpgradeRequest` | `CardUpgradeResponse` | `request_id` 或 envelope nonce 去重 |
| `decks.list` | 空对象 | `DeckListResponse` | 只读 |
| `decks.save` | `SaveDeckRequest` | `SaveDeckResponse` | storage version + request id |

`CardUpgradeRequest`：

```json
{
  "card_id": "draw_sigil",
  "target_level": 2,
  "client_result_authoritative": false
}
```

`SaveDeckRequest`：

```json
{
  "deck_id": "http_active",
  "name": "Practice",
  "format": "ranked",
  "card_ids": ["draw_sigil"],
  "active": true,
  "updated_at": "2026-10-07T00:00:00Z"
}
```

实现时 `card_ids` 必须是完整 20 张牌；上面的 JSON 只展示字段形状，不是
可通过校验的完整卡组。

`InventorySnapshot` 必须返回：

```json
{
  "ok": true,
  "user_id": "user_x",
  "ruleset_version": "ruleset-local-s0",
  "items": [
    {
      "card_id": "draw_sigil",
      "copies": 2,
      "level": 1,
      "first_obtained_at": "2026-10-07T00:00:00Z"
    }
  ],
  "server_authoritative": true,
  "server_time": "2026-10-07T00:00:00Z"
}
```

`DeckListResponse` 必须返回 `active_deck_id`、`ruleset_version`、完整
`decks[]`、`server_authoritative` 和 `server_time`。`SaveDeckResponse` 必须
返回服务端重建后的 `deck`、`active_deck_id`、`validation`，不能回显未经
校验的客户端 card list 作为权威结果。

### Nakama storage

| collection | key | owner | 读写 | 内容 |
| --- | --- | --- | --- | --- |
| `player_wallet` | `user_id` | `user_id` | Runtime 读写 | `points`、`card_dust`、`chest_keys`、`updated_at` |
| `player_card_inventory` | `user_id` | `user_id` | Runtime 读写 | `items[]`，每项 card/copies/level/first_obtained_at |
| `player_decks` | `user_id` | `user_id` | Runtime 读写 | `active_deck_id`、`decks[]`、每个 deck 的 revision |
| `card_catalog` | `ruleset_version` | 空 | Runtime 只读 | 卡牌合法性、稀有度、升级上限、禁卡和格式标签 |
| `economy_operation` | `request_id` | `user_id` | Runtime 创建 | 升级扣费、钱包/库存变更前后 hash 和结果 |

本切片不使用 leaderboard。`rank_score` 等 leaderboard 只能在结算/评级
切片中写入；保存卡组不得改变排行榜。

建议的 storage value 最小字段：

```json
{
  "schema_version": 1,
  "ruleset_version": "ruleset-local-s0",
  "revision": 3,
  "updated_at": "2026-10-07T00:00:00Z",
  "payload": {}
}
```

所有写操作先读 `version`，再用 Nakama storage write 的 version 条件提交。
版本冲突返回 `storage_conflict`，客户端重新拉取后再决定是否重试。

### 服务端校验与错误码

- `invalid_request`：字段缺失、`target_level` 越界或 card id 为空；
- `invalid_deck`：20 张牌、重复数量、拥有量、禁卡、格式或 ruleset 不合法；
- `not_found`：card 或 deck 不存在；
- `insufficient_resource`：粉尘/钱包不足；
- `forbidden_field`：`client_result_authoritative=true`；
- `storage_conflict`：并发保存版本落后；
- `operation_duplicate`：同一 request id 已成功执行，返回原结果而不重复扣费。

升级操作必须在一个 Runtime 事务边界内完成：读取 wallet/inventory/catalog，
校验成本和等级，写 `economy_operation` 幂等记录，再写 wallet/inventory。
如果 Nakama storage 没有跨对象事务能力，实现必须使用 operation 状态机：
`pending -> applied`，重试时按 operation record 恢复，不得再次扣费。

## 客户端接入点

SpellKard 现有入口保持不变：

- `godot/scripts/gensoulkyo_http_client.gd::sync_inventory()`；
- `godot/scripts/gensoulkyo_http_client.gd::sync_decks()`；
- `godot/scripts/gensoulkyo_http_client.gd::save_active_deck()`；
- `godot/scripts/gensoulkyo_api_model.gd::inventory_request()`；
- `decks_request()`、`save_deck_request()`；
- `apply_inventory_response()`、`apply_decks_response()`、
  `apply_deck_save_response()`；
- `godot/scripts/matchmaking_model.gd` 读取 `active_deck_id`，但不允许用
  本地 card list 覆盖服务端已保存的 deck snapshot。

兼容期客户端仍可走 HTTP fallback；Nakama RPC transport 必须返回同一 payload
字段名和 authority 标记。升级成功后客户端只应用服务端返回的 inventory/wallet，
不得本地先加等级或扣粉尘。

## 数据迁移与切换

源数据来自 Gensoulkyo `userState` 对应字段和未来一次性导出快照：

- `Wallet` -> `player_wallet.payload`；
- `Inventory` -> `player_card_inventory.payload.items`；
- `Decks` + `ActiveDeckID` -> `player_decks.payload`；
- `RulesetVersion` 写入各对象的顶层 `ruleset_version`；
- 当前没有稳定 request id 的历史升级操作不得伪造
  `economy_operation`，只导入最终余额/库存/卡组状态。

迁移步骤：

1. 导出每个 user 的 wallet/inventory/decks，按 user id 排序并计算
   `source_revision`。
2. 先导入 wallet、inventory、decks，再运行 validator；任一 card 不在
   `card_catalog` 或卡组不满足 20 张规则时整户进入 quarantine，不可部分
   切换。
3. 开启双读：Nakama 对象完整且 ruleset 一致时为主，否则读 legacy。
4. 对升级和卡组保存启用双写，但只允许 Nakama 结果回传客户端；legacy
   写入失败进入 outbox/告警，不得回退为客户端成功。
5. 连续一轮服务端/客户端回归通过，且抽样用户 projection hash 一致后，
   切换为 Nakama-only。

## 回滚策略

- 发现 storage version、扣费或 deck validation 不一致时，关闭
  `inventory.get`/`decks.*` 的 Nakama write flag，保留只读导入数据。
- 读路径回到 legacy snapshot；已经成功的 `economy_operation` 通过 request
  id 去重，禁止自动反向发放或重复扣费。
- 回滚期间禁止切换 active deck 进入排位，直到 `ruleset_version` 和
  projection hash 恢复一致。
- 修复后只能从最后一个一致的 `source_revision` 重建未切换用户；已在
  Nakama-only 阶段产生的新数据必须先导出再合并，禁止旧快照覆盖新数据。

## 验收测试

服务端最小命令：

```sh
cd /root/gotouhou/Gensoulkyo
go test ./runtime/... ./cmd/gensoulkyo_nakama
docker-compose --profile test run --rm test
```

必须断言：

- 新用户 bootstrap 有默认 inventory/deck，且 `server_authoritative=true`；
- `inventory.get`、`decks.list` 与 bootstrap 使用相同 ruleset 和 user id；
- 非拥有卡、20 张以外卡组、重复超过限制、排位禁卡均拒绝；
- 并发 `decks.save` 的旧 storage version 返回 `storage_conflict`；
- 重试同一个 upgrade request id 不会再次扣 card_dust；
- `client_result_authoritative=true` 永远拒绝；
- 升级/保存卡组不写任何 leaderboard。

跨仓合同与安全边界：

```sh
python3 /root/gotouhou/docs/ops/protocol_audit_check.py
```

客户端最小命令：

```sh
cd /root/gotouhou/SpellKard
python3 tools/ci_static_checks.py
/root/gotouhou/Godot_v4.7-stable_linux.x86_64 --headless \
  --path godot --script ../tools/client_smoke_test.gd
```

可选的真实 Nakama tag-build：

```sh
cd /root/gotouhou/Gensoulkyo
docker-compose --profile nakama-tag-build run --rm nakama-tag-build
```

若该命令因 SDK 下载或网络失败，只能标为环境阻塞；本切片的本地 Go 合同
测试不能替代真实 plugin build。

## 依赖与交付边界

- 前置：`01-login-and-bootstrap.md` 的 Nakama user/session 映射与
  `card_catalog` 版本锁定。
- 后置：宝箱/奖励切片必须复用 `player_wallet`、`player_card_inventory`，
  不能复制一套库存表。
- `active_deck_id` 只决定下一次业务匹配读取的 deck snapshot；战斗服仍只
  接收 Nakama 签发的 snapshot/hash，不能直接读 storage。

