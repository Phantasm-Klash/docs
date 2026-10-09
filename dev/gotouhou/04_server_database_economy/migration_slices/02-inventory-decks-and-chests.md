# 02 库存、卡组、卡牌与宝箱

## 目标和边界

把玩家资产的读取、卡组保存、卡牌升级和服务端开箱迁移到 Nakama
storage/Go Runtime。钱包、库存、卡组和宝箱必须以服务端写入为准；客户端
只能提交意图，不能提交最终数量、掉落、卡牌等级或消费后的余额。
本切片不实现活动奖励、商店购买、匹配或 leaderboard 写入。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | Nakama authenticated `user_id`、业务 envelope、deck/chest/card intent、幂等键 |
| 输出 | `InventorySnapshot`、`DeckListResponse`、`ChestSnapshot`、升级/开箱后的 wallet 与 grant |
| 前置依赖 | `01-auth-and-bootstrap`、卡牌/模式 ruleset、钱包与掉落表、业务 envelope guard |
| 下游切片 | `03-matchmaking-rooms-and-lobby` 使用已校验 deck snapshot；`06` 读取资产并发奖励 |
| 实现归属 | `nakama-server-agent`：Runtime RPC、storage transaction、掉落/升级校验；`client-agent`：Collection/Deck/Chest 接入 |

## 当前 Gensoulkyo 的岗位

- `inventory.get` 返回服务端 inventory/wallet snapshot。
- `decks.list`、`decks.save` 维护牌组并在进入匹配时生成
  `deck_snapshot`/`deck_snapshot_hash`。
- `cards.upgrade` 校验升级成本、最大等级和库存扣减。
- `chests.list`、`chests.open` 管理宝箱、钥匙、pity 和掉落。
- 当前默认数据由 `LoginAnonymous` 初始化；迁移期部分状态仍可能在 core
  内存，不能以客户端 bootstrap 结果作为数据源。

## 目标 Nakama 契约

### RPC

| RPC | 输入 | 输出/副作用 | 错误码 |
| --- | --- | --- | --- |
| `inventory.get` | 无业务字段 | wallet、items、cards、server time、版本 | `unauthorized`, `storage_unavailable` |
| `decks.list` | 无业务字段 | decks、active deck、validation metadata | 同上 |
| `decks.save` | `deck_id`、卡牌/角色列表、`client_revision`、`idempotency_key` | canonical deck、validation、snapshot hash | `deck_invalid`, `revision_conflict`, `idempotency_conflict` |
| `cards.upgrade` | `card_id`、目标等级或 upgrade intent、`idempotency_key` | canonical card、cost、wallet/inventory delta、ledger id | `card_not_owned`, `max_level`, `insufficient_currency` |
| `chests.list` | 无业务字段 | chest instances、pity、keys、pool version | 同上 |
| `chests.open` | `chest_id`、`pool_version`、`idempotency_key` | server roll、grants、wallet/inventory delta、opening id | `chest_not_owned`, `pool_version_mismatch`, `already_processed` |

响应都带 `server_time`、`ruleset_version` 和 `server_authoritative: true`。
写 RPC 要求业务 envelope 的 `op` 与 RPC 一致，幂等键必须绑定
`user_id + operation + request_hash`；相同请求重试返回原结果，不得再次扣费
或发奖。

### Storage collection/key

| collection | key | 内容 |
| --- | --- | --- |
| `player_wallet` | `user_id` | currencies、chest_keys、revision、updated_at |
| `player_inventory` | `user_id` | item/card quantities、card levels、revision、updated_at |
| `player_decks` | `user_id` | canonical decks、active deck、revision、snapshot hash |
| `player_chests` | `user_id` | chest instances、pity counters、pool versions |
| `chest_openings` | `user_id:opening_id` | request hash、roll seed hash、grants、before/after revisions、status |
| `economy_ledger` | `user_id:ledger_id` | debit/credit、reason、source、idempotency key、balance hash |
| `card_catalog` | `catalog_version` | 只读卡牌定义、升级曲线、禁用标记 |
| `chest_pools` | `pool_version` | 只读掉落表、权重、保底规则、配置 hash |

写入应使用 Nakama storage version/conditional write，或在 Go Runtime 中用
事务型 repository 保证 wallet、inventory、ledger 一致。`card_catalog` 和
`chest_pools` 不允许客户端写入。此切片不写 leaderboard；排行榜只在
`06` 处理活动/赛季或结算事件。

## 客户端接入点

- `lobby_client.ts` 已有 `call()`、session、bootstrap 和业务 envelope
  基础；由 `client-agent` 增加 `getInventory()`、`listDecks()`、
  `saveDeck()`、`upgradeCard()`、`listChests()`、`openChest()`。
- Collection 页面接入 `inventory.get`；卡牌页面显示服务端 cost/max level
  并在成功响应后替换本地快照；Deck 页面只提交选中的 card ids 和 revision；
  Chest 页面用服务端 grants 播放动画，不能本地抽样。
- `lobby_flow.ts` 的 `signIn()` 只负责 bootstrap；进入 Collection 时按需
  拉取细分快照，返回 Lobby 不清空 session。
- 网络层只使用 Nakama HTTPS RPC；WSS 只推送资产变更通知或活动通知，
  不在客户端通过 WSS 直接改库存。

## 数据迁移

1. 从旧 `player_wallets`、`player_card_inventory`、`player_decks`、
   `chest_openings`/内存 chest state 导出 canonical JSON 和源 revision。
2. 按 `identity_link` 映射到 Nakama `user_id`，先导入 wallet/inventory，
   再导入 decks/chests，最后导入 ledger/opening audit；导入顺序避免把
   未拥有卡牌写入 deck。
3. 每个用户写入 `migration_batch_id`、源快照 hash、目标 revision 和
   `migrated_at`。导入前运行 card catalog/pool version 兼容检查。
4. 初期双读比较数量、等级、active deck snapshot hash 和 pity。发现差异时
   保留旧快照和 Nakama rejected reason，停止该用户切换，不自动合并。
5. 对进行中的 `chests.open` 只迁移已落账 opening；未完成请求作废并要求
   重新发起，不能重复发放。

## 回滚策略

- `economy_read_source` 支持 `legacy`、`shadow`、`nakama`；写入切换前先
  只读双写审计，切换后只允许一个权威写源。
- Nakama 写入异常时可回退到 legacy 读路径，但已成功写入的 Nakama ledger
  不在旧系统重放；以 `idempotency_key` 对账后再决定补偿。
- `decks.save` 冲突只回滚本次 revision；保留上一版 canonical deck。
  `cards.upgrade`/`chests.open` 失败不做客户端侧补偿，需由服务端 ledger
  反向交易或人工审计。
- 出现掉落表 hash 不一致时立即禁用 `chests.open`，不回退到客户端随机。

## 验收测试

### 服务端

- 读取接口只返回当前 user 的数据；篡改 user id、越权 collection key 和
  未认证请求均失败。
- `decks.save` 拒绝非法卡牌、重复卡、禁用卡、旧 revision，并返回稳定
  validation；重试相同幂等键只产生一次写入。
- `cards.upgrade` 在余额不足、满级、卡牌不存在时不改变 wallet/inventory；
  并发升级不会双扣。
- `chests.open` 使用服务端 pool version/随机源，重复 opening 不重复发奖；
  `chest_openings`、ledger、inventory 三者可按 opening id 对账。
- storage 重启/写冲突后可恢复；bootstrap 汇总与细分 RPC 的 revision/hash
  一致；所有 grant 都有审计记录且不含秘密。
- 运行对应 Go Runtime/unit/storage tests；使用 Nakama `docker-compose`
  启动 PostgreSQL/Nakama 做一轮真实 conditional-write 与重启测试。

### 客户端

- Collection/Deck/Chest 页面能解析成功和业务错误，不把失败响应当作本地
  成功；重复点击只发同一幂等请求或安全复用结果。
- 保存 deck 后显示服务端 canonical 顺序和 snapshot hash；匹配前使用该
  hash，不使用未保存的本地草稿。
- 开箱动画只消费 `grants`，断线重连后按 opening id 查询/恢复，不重新抽取。
- client build 的 HTTPS live check 覆盖空库存、revision conflict、版本过期、
  网络重试和重新登录后的数据恢复。

## 明确不在范围内

商店/Steam 交易、活动领取、赛季排名、战斗结算奖励、房间创建和 battle
ticket 不在本切片；这些功能必须通过本切片提供的 canonical asset/ledger
接口接入。
