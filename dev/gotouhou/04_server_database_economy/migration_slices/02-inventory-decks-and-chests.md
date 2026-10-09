# 02 库存、卡组、卡牌与宝箱

## 目标和边界

把玩家资产的读取、卡组保存、卡牌升级和服务端开箱迁移到 Nakama
storage/Go Runtime。钱包、库存、卡组和宝箱必须以服务端写入为准；客户端
只能提交意图，不能提交最终数量、掉落、卡牌等级或消费后的余额。
本切片不实现活动奖励、商店购买、匹配或 leaderboard 写入。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | Nakama authenticated `user_id`、业务 envelope、deck/card/chest intent、`client_revision`、`idempotency_key` |
| 输出 | `InventorySnapshot`、`DeckListResponse`、`ChestSnapshot`、canonical deck hash、升级/开箱后的 wallet/inventory delta、ledger/operation receipt |
| 前置依赖 | `01-auth-and-bootstrap`、卡牌/模式 ruleset、钱包与掉落表、业务 envelope guard、Nakama `3.41.0` Storage API 与 server-side storage permissions |
| 下游切片 | `03-matchmaking-rooms-and-lobby` 使用已校验 deck snapshot；`06` 读取资产并发奖励 |
| 实现归属 | `nakama-server-agent`：Runtime RPC、storage transaction、掉落/升级校验；`client-agent`：Collection/Deck/Chest 接入 |

本切片的独立交付边界：

| Owner | 输入 | 必须交付的输出 | 不得接管 |
| --- | --- | --- | --- |
| `nakama-server-agent` | `ctx.UserID`、catalog/pool version、旧资产导出、业务 envelope | 六个 RPC、资产 storage schema、事务/条件写、幂等 operation receipt、迁移 importer、审计查询 | 商店商品目录、活动 claim、匹配/结算 leaderboard |
| `client-agent` | RPC response/error contract、Nakama session、Collection route | inventory/card/deck/chest decoder、revision/idempotency 重试、服务端 grants 展示、`chests.list` route 对齐 | 本地抽卡、余额预扣、客户端 owner/reward 写入 |

## 可直接开工的交付边界

服务端 agent 以 `01` 产出的 Nakama `user_id` 为唯一 owner，交付六个玩家
RPC、一个幂等 operation collection 和两个只读配置集合。实现顺序固定为
`inventory.get` -> `decks.list/save` -> `cards.upgrade` ->
`chests.list/open`；每一步都必须能独立回放和对账。

| 入口 | Nakama 面 | 输入类型 | 输出类型 | 写入集合 |
| --- | --- | --- | --- | --- |
| `inventory.get` | authenticated custom RPC | `EmptyRequest` | `InventorySnapshot` | 无 |
| `decks.list` | authenticated custom RPC | `EmptyRequest` | `DeckListResponse` | 无 |
| `decks.save` | authenticated custom RPC | `SaveDeckRequest` | `SaveDeckResponse` | `player_decks`、`asset_operations`（不产生 economy ledger） |
| `cards.upgrade` | authenticated custom RPC | `CardUpgradeRequest` | `CardUpgradeResponse` | `player_wallet`、`player_inventory`、`economy_ledger`、`asset_operations` |
| `chests.list` | authenticated custom RPC | `EmptyRequest` | `ChestSnapshot` | 无 |
| `chests.open` | authenticated custom RPC | `ChestOpenRequest` | `ChestOpenResponse` | `player_wallet`、`player_inventory`、`player_chests`、`chest_openings`、`economy_ledger` |

`card_catalog` 与 `chest_pools` 是 Go Runtime 管理的只读 storage；它们不是
leaderboard，也不接受客户端写入。`asset_operations` 保存同一
`idempotency_key` 的最终响应和 request hash；它不是经济余额。此切片不调用
Nakama leaderboard write API，不能把升级次数、开箱次数或钱包余额写成排行
榜分数。`03` 只消费 `DeckSnapshot` 和 `deck_snapshot_hash`，不得读取客户
端本地草稿。

## 当前 Gensoulkyo 的岗位

- `inventory.get` 返回服务端 inventory/wallet snapshot。
- `decks.list`、`decks.save` 维护牌组并在进入匹配时生成
  `deck_snapshot`/`deck_snapshot_hash`。
- `cards.upgrade` 校验升级成本、最大等级和库存扣减。
- `chests.list`、`chests.open` 管理宝箱、钥匙、pity 和掉落。
- 当前默认数据由 `LoginAnonymous` 初始化；`userState`、wallet、inventory、
  decks、chests、pity 和 opening log 默认都在 `runtime/core` 进程内存，
  没有可供导入器读取的资产 repository。没有旧快照时只能标记
  `new_account`/`reconciliation_required`，不能把重新初始化的默认资产
  当作历史迁移结果。
- 当前 `CardUpgradeRequest`、`SaveDeckRequest`、`ChestOpenRequest` 没有
  `client_revision`/`idempotency_key`；业务 envelope 的 `seq`/`nonce` 只
  防运输层重放，不能替代资产操作幂等。server agent 必须新增 operation
  receipt，而不是把 envelope nonce 当 ledger id。
- 当前 `OpenChest` 按 `pool_id + count` 消耗 pool 计数，**没有 chest_id
  实例**；目标不得凭空引入 chest instance。`ChestOpeningRecord` 当前还
  带 `ServerSeed`，目标响应只返回 `seed_hash`/opening id，不能向客户端
  暴露可用于重算掉落的 seed。
- 当前 `InventorySnapshot` 没有 `wallet`、revision 或 snapshot hash；
  Laya `fetchInventory()` 对缺失 wallet 会静默得到空 map。目标 adapter
  必须补齐 canonical wallet/revision，不能把当前空 map 当真实余额。
- 当前 Nakama dispatcher 支持 `chests.list`/`chests`，不支持
  `chests.get`；Laya fallback 仍调用 `chests.get`。client agent 必须保留
  `fetchChests()` 公共方法，但 Nakama transport 统一发 `chests.list`，
  fallback 才可保留旧 alias。

代码对照入口：
`Gensoulkyo/runtime/core/service.go` 的 `Inventory`、`Decks`、`SaveDeck`、
`UpgradeCard`、`Chests`、`OpenChest`，以及
`Gensoulkyo/runtime/nakamaapi/handler.go` 的同名 RPC case。客户端对照入口：
`SpellKard/laya/src/core/net/lobby_client.ts`、`lobby_flow.ts`、
`platform/laya/scenes/inventory_scene.ts`。

## 目标 Nakama 契约

### RPC

| RPC | 输入 | 输出/副作用 | 错误码 |
| --- | --- | --- | --- |
| `inventory.get` | `{}` | `InventorySnapshot{wallet,items,asset_revision,snapshot_hash}` | `unauthorized`, `storage_unavailable` |
| `decks.list` | `{}` | `DeckListResponse{decks,active_deck_id,asset_revision,snapshot_hashes}` | `unauthorized`, `storage_unavailable` |
| `decks.save` | `SaveDeckRequest{deck_id,name,format,card_ids,active,client_revision,idempotency_key}` | canonical deck、validation、`deck_snapshot_hash`、new `asset_revision`、operation receipt | `deck_invalid`, `revision_conflict`, `idempotency_conflict` |
| `cards.upgrade` | `CardUpgradeRequest{card_id,target_level,client_revision,idempotency_key}` | canonical card、cost、wallet/inventory delta、ledger id、new `asset_revision`、operation receipt | `card_not_owned`, `max_level`, `insufficient_currency`, `revision_conflict` |
| `chests.list` | `{}` | `ChestSnapshot{owned_chests,pity_counters,pool_version,asset_revision,opening summaries}` | `unauthorized`, `storage_unavailable` |
| `chests.open` | `ChestOpenRequest{pool_id,count,pool_version,client_revision,idempotency_key}` | server roll、grants、wallet/inventory delta、opening id/hash、new `asset_revision`、operation receipt | `chest_not_owned`, `pool_version_mismatch`, `already_processed`, `revision_conflict` |

响应都带 `server_time`、`ruleset_version`、`server_authoritative: true`、
`operation_id`（写操作）和 owner-independent `snapshot_hash`。请求中不得接受
`user_id`、`wallet`、`inventory`、`grants`、`server_seed`、
`client_result_authoritative` 或最终等级作为权威字段；若出现这些字段，
返回 `forbidden_field`，不能静默合并。
写 RPC 要求业务 envelope 的 `op` 与 RPC 一致，幂等键必须绑定
`user_id + operation + request_hash`；相同请求重试返回原结果，不得再次扣费
或发奖。

写请求的 body contract：

```json
{
  "card_id": "focus_lens",
  "target_level": 2,
  "client_revision": 7,
  "idempotency_key": "opaque-client-operation-id"
}
```

`idempotency_key` 是业务操作键，必须由客户端在一次用户意图开始时生成并
在网络重试中复用；envelope `nonce` 是传输层字段，两者不能互换。相同 key
但 request hash 不同返回 `idempotency_conflict`，相同 key/hash 返回保存的
canonical response 并标记 `duplicate=true`。

字段类型以 JSON/Go 对照为准：`int64` 在 JSON 中编码为整数，时间用 RFC3339 UTC；
所有 `user_id` 均从 Nakama auth context 派生，不出现在 request type。

```text
EmptyRequest = {}
InventorySnapshot = {
  ok: bool, user_id: string, ruleset_version: string,
  wallet: map<string,int>, items: CardInventoryEntry[],
  asset_revision: int64, snapshot_hash: "sha256:<hex>",
  server_authoritative: true, server_time: RFC3339
}
CardInventoryEntry = {
  card_id: string, copies: int, level: int, first_obtained_at: RFC3339
}
SaveDeckRequest = {
  deck_id?: string, name: string, format: string, card_ids: string[20],
  active: bool, client_revision: int64, idempotency_key: string
}
SaveDeckResponse = {
  ok: bool, deck: DeckRecord, active_deck_id: string,
  deck_snapshot_hash: "sha256:<hex>", asset_revision: int64,
  operation_id: string, duplicate: bool, server_time: RFC3339
}
CardUpgradeRequest = {
  card_id: string, target_level: int,
  client_revision: int64, idempotency_key: string
}
CardUpgradeResponse = {
  ok: bool, card_id: string, old_level: int, new_level: int, max_level: int,
  cost: map<string,int>, wallet: map<string,int>,
  inventory: InventorySnapshot, ledger_id: string, asset_revision: int64,
  operation_id: string, duplicate: bool, server_time: RFC3339
}
ChestOpenRequest = {
  pool_id: string, count: int, pool_version: string,
  client_revision: int64, idempotency_key: string
}
ChestOpenResponse = {
  ok: bool, pool_id: string, count: int, wallet: map<string,int>,
  owned_chests: map<string,int>, inventory: InventorySnapshot,
  pity_counters: map<string,ChestPityState>, results: ChestOpenResult[],
  audit: {opening_id:string, pool_version:string, cost:map<string,int>,
          seed_hash:string, grants:GrantEntry[], opened_at:RFC3339},
  ledger_id: string, asset_revision: int64, operation_id: string,
  duplicate: bool, server_time: RFC3339
}
```

`DeckListResponse` 和 `ChestSnapshot` 复用上述 snapshot 字段：前者包含
`active_deck_id`、`decks: DeckRecord[]`、deck hashes、`asset_revision`；后者包含
`wallet`、`owned_chests`、`pools: ChestPool[]`、`pity_counters`、
opening summaries、`asset_revision`。`ChestOpeningRecord` 的旧 `server_seed` 字段
不出现在任何 Nakama player response。

### Storage collection/key

每个玩家数据对象的 Nakama storage owner 固定为 `ctx.UserID`；表内 key 不再
重复拼接 user id。所有 collection 的客户端权限固定为
`permission_read=0`、`permission_write=0`，客户端只能通过本切片 RPC 访问；
Go Runtime 使用 server-side storage API。版本字段必须从 Nakama
`StorageObject.Version` 条件写入。玩家对象由 `ctx.UserID` 隔离；配置对象由
server/admin owner 写入，不能被客户端直接读取或修改。

| collection | key | permission_read | permission_write | 内容/条件 |
| --- | --- | ---: | ---: | --- |
| `player_asset_revision` | `primary` | 0 | 0 | `asset_revision`、`snapshot_hash`、`updated_at`；玩家资产域共享水位和条件写锚点 |
| `player_wallet` | `primary` | 0 | 0 | `currencies`、局部 `revision`、`updated_at`；所有扣款/入账都递增局部 revision |
| `player_inventory` | `primary` | 0 | 0 | `cards[{card_id,copies,level,first_obtained_at}]`、局部 `revision`、`snapshot_hash` |
| `player_decks` | `primary` | 0 | 0 | `decks[]`、`active_deck_id`、局部 `revision`、每副牌 `deck_snapshot_hash` |
| `player_chests` | `primary` | 0 | 0 | `owned_chests{pool_id:count}`、`pity_counters`、`pool_version_by_id`、局部 `revision` |
| `chest_openings` | `<opening_id>` | 0 | 0 | request hash、pool version、seed hash、grants、before/after `asset_revision`、status、server time |
| `economy_ledger` | `<ledger_id>` | 0 | 0 | debit/credit、reason、source、operation id、before/after wallet hash、`asset_revision` |
| `asset_operations` | `sha256:<idempotency_key_hash>` | 0 | 0 | operation、request hash、response snapshot、receipt id、status；相同 owner/key 唯一 |
| `card_catalog` | `<catalog_version>` | 0 | 0 | 只读卡牌定义、升级曲线、禁用标记、配置 hash；server/admin write only |
| `chest_pools` | `<pool_version>:<pool_id>` | 0 | 0 | 只读掉落表、权重、保底规则、生效区间、配置 hash；server/admin write only |

`player_asset_revision/primary` 中的 `asset_revision` 是每个用户资产域的
唯一单调水位，初始为 `1`。所有写 RPC 读取并校验
`client_revision == asset_revision`，成功时必须把
`player_asset_revision/primary` 与所有受影响对象在同一 batch 内写成同一个
`asset_revision + 1`；`player_asset_revision` 必须出现在每次资产 mutation
的 read-modify-write batch 中。只读 RPC 读取多个对象时先后检查该水位，发现
不一致就重读，不能返回跨 revision 拼接的快照。`wallet`、`inventory`、
`decks`、`player_chests` 的局部 `revision` 只供审计或迁移对照，客户端并发
条件和所有 response 字段统一使用 `asset_revision`，不得另造对外的 revision
别名。

Nakama leaderboard id：**无**；本切片不得注册或调用 leaderboard write。

`decks.save` 只更新 `player_decks`、`player_asset_revision` 与
`asset_operations`，不写 `economy_ledger`。`cards.upgrade` 与 `chests.open`
会同时更改 wallet、inventory、chest/pity、`player_asset_revision` 和
ledger/receipt，必须把所有对象放进**一次** `nk.StorageWrite(ctx, writes)`
调用，并为每个 read-modify-write 对象带回 `StorageObject.Version` 条件；
不能拆成多个 `StorageWrite`。

Nakama `3.41.0` 的 Storage Engine 在 PostgreSQL transaction 内写完整个
batch；任一对象的 version/权限校验失败，整批失败。server agent 必须保留
该单 batch 边界，不直接修改 Nakama 的 `storage` 表，也不为这组对象新增
自定义 SQL DDL。

业务实现顺序：

1. 先按 owner/key 读 operation receipt；存在且 request hash 一致则返回
   原响应（`duplicate=true`），hash 不一致返回 `idempotency_conflict`。
2. 读取 wallet/inventory/chest 当前值和 Nakama version，服务端校验成本、
   数量、ruleset/pool version、pity 和 deck ownership。
3. 在内存构建全部 after-state，并一次性 batch 写所有变化对象。已有对象传
   exact version，新建 receipt/opening/ledger object 传 Nakama create-only
   version `*`，避免并发重试生成两笔操作。
4. 若 batch 返回 version conflict，重读 receipt：相同 request hash 已提交
   则返回原结果；否则返回 `revision_conflict`，不得部分成功或自动再开箱。

本规格把货币保存在 `player_wallet/primary`，因此不调用 Nakama 原生
`WalletUpdate`。若实现者改选 Nakama Wallet API，必须把资产变更改为
`nk.MultiUpdate`（storage writes + wallet update + ledger）并重新冻结 response
contract；不能同时维护两个 gold/gems 权威。

`card_catalog` 和 `chest_pools` 不允许客户端写入。此切片不写 leaderboard；
排行榜只在 `06` 处理活动/赛季或结算事件。

### 资产不变量和错误映射

- `deck_snapshot_hash = sha256(canonical_json({deck_id,name,ruleset_version,card_ids}))`
  并带 `sha256:` 前缀；canonical `card_ids` 顺序由服务端保存，匹配时只读
  `player_decks/primary`，不信任 `deck_snapshot` 请求副本。
- 当前牌组规则保留 20 张、单卡最多 2 张、只能使用已拥有卡、ruleset
  一致、ranked 禁卡/高稀有度/强干扰上限。规则失败统一映射
  `deck_invalid`，不要把 Go core 的多种 `invalid_request` 直接暴露给客户端。
- 当前宝箱模型是 `pool_id` 的拥有数量；`chests.open` 的 canonical 请求是
  `pool_id` + `count`，不是 `chest_id`。`count` 目标限制为 `1..10`，
  `pool_version` 必须等于服务端当前池版本；服务端产生 `opening_id`、
  `seed_hash` 和 grants，客户端不能提交 seed、rarity、card id 或结果。
- `cards.upgrade` 只接受当前等级的下一等级；`target_level` 不是客户端可
  自由设置的最终状态。余额不足、未拥有、满级、revision 过期分别返回
  `insufficient_currency`、`card_not_owned`、`max_level`、
  `revision_conflict`。
- `chests.open`、`cards.upgrade` 成功后同时返回新的 wallet/inventory
  snapshot hash；客户端丢响应时用同一 `idempotency_key` 重放并得到
  `duplicate=true`，不能发起新 key 的“补偿购买/开箱”。

## 客户端接入点

- `SpellKard/laya/src/core/net/lobby_client.ts` 已有以下 public methods：
  `fetchInventory()`、`fetchChests()`、`openChest()`、`fetchDecks()`、
  `saveDeck()`；`client-agent` 应保留这些调用点，在 Nakama transport 中
  映射到 `inventory.get`、`chests.list`、`chests.open`、`decks.list`、
  `decks.save`。新增 `upgradeCard(cardId,targetLevel,revision,key)`。
- 现有 Laya `fetchChests()` 调用 id=`chests.get`，但服务端 contract
  registry 是 `chests.list`。Nakama transport 应在 transport adapter 内做
  alias normalization；service runtime 不必再注册第二个 `chests.get` RPC。
  旧 HTTP fallback 可暂时继续走 `/v1/chests`。
- `lobby_client.ts` 的写方法补齐 `client_revision` 和稳定
  `idempotency_key`；待响应/超时重试保留 key 和原 body，成功后才替换本地
  wallet/inventory/deck/chest projection。Revision conflict 需先 reload，
  不得自动改 key 再提交。
- `SpellKard/laya/src/core/game/lobby_flow.ts` 的
  `openInventory()` 当前只拉 inventory；Collection enter 时还需加载
  `fetchChests()`/`fetchDecks()`，页面返回 Lobby 不清空 Nakama session。
- `SpellKard/laya/src/platform/laya/scenes/inventory_scene.ts` 是当前已存在的
  Collection UI 接入点：宝箱按钮只从 `ChestOpenResponse.results` 播放服务端
  结果，断线后由同一 opening/operation receipt 恢复；不在客户端 roll。
  Deck/card upgrade 页面尚无独立 Laya scene，本切片需 client agent 加入
  Collection route 或在既有 scene 内交付可测表单，不得把其描述为已存在。
- 写 RPC 只使用 Nakama HTTPS RPC；WSS 若推送 `economy.updated`，payload
  只携带已提交 revision/operation id，客户端仍需用 RPC 拉 canonical
  snapshot。WSS 不接受资产写入。

## 数据迁移

1. 先确认旧权威数据源。目标导入格式为 canonical JSON manifest：
   `legacy_user_id`、wallet、card inventory、decks、owned chest counts、
   pity、已落账 opening、每个源 revision 和 source snapshot hash。仓库现有
   `database_schema.md` 的旧 SQL 名称是 `player_wallets`、
   `player_card_inventory`、`player_decks`、`chest_openings`，但当前
   Gensoulkyo 默认只有内存 `userState`，没有可直接读取的 `player_wallets`
   等真实表；没有外部导出时只能把用户标为 `reconciliation_required`，
   不能从 `LoginAnonymous` 默认种子推导历史资产。
2. 按 `01` 的 `identity_link` 映射到 Nakama `user_id`，先导入
   `player_wallet/primary`、`player_inventory/primary`，再导入
   `player_decks/primary`、`player_chests/primary`，最后导入
   `economy_ledger`/`chest_openings`/`asset_operations` audit。任何 deck
   卡牌数量超过已导入 inventory 时整批 rejected，不允许部分激活。
3. 映射必须显式配置货币和 id：
   `player_wallets.points`、`card_dust`、`chest_keys` 不能猜测为
   `gold`/`gems`；若 `points -> gold` 是产品决策，必须写入 versioned
   mapping manifest 并在 shadow diff 中报告。`player_card_inventory.card_id`
   与 Nakama `card_id` 的 UUID/code 映射缺失时整批 rejected；不得按名称模糊
   匹配。`player_decks.card_ids` 的顺序必须原样保留，不能为了 canonical
   hash 排序。
4. 导入前锁定并校验 `catalog_version`、每个 `pool_id` 的 `pool_version`、
   ruleset version；被禁用或不存在的卡牌/池进入 rejected manifest，不能
   静默转换为其他卡或默认池。
5. 每个用户写入 `migration_batch_id`、source/target snapshot hash、源/目标
   revision、catalog/pool version、`migrated_at`；目标 operation key 使用
   `source_import:<batch_id>:<legacy_operation_id>`，避免导入重跑重复扣款
   或发奖。
6. 初期双读比较 wallet、card copies/levels、active deck snapshot hash、
   owned chest count、pity 和最后 opening id。差异保留旧快照与 Nakama
   rejected reason，停止该用户切换，不自动合并。
7. 对进行中的 `chests.open` 只迁移已落账 opening；无明确 committed/
   rejected 状态的请求标为 `needs_retry`，不得把未知状态重新发奖。重试必须
   由新业务操作显式发起并产生新 opening id。

迁移记录必须能以 `user_id + migration_batch_id` 查询，并至少保存
`source_snapshot_hash`、`source_revision`、`target_revision`、
`catalog_version`、`pool_version`、`deck_snapshot_hash`、
`last_opening_id`、`status` 和 `rejected_reason`。导入器必须先写
`player_wallet`/`player_inventory`，再写 `player_decks`；任何 deck 中的
卡牌数量超过已导入 inventory 时，该用户批次进入 `rejected`，不得部分激活。

## 回滚策略

- `economy_read_source` 支持 `legacy`、`shadow`、`nakama`；写入切换前先
  只读双写审计，切换后只允许一个权威写源。
- Nakama 写入异常时可回退到 legacy 读路径，但已成功写入的 Nakama ledger
  不在旧系统重放；按 `asset_operations`/`idempotency_key` 对账后再决定
  服务端补偿。
- 资产写 authority 切换必须按用户或批次边界完成，不允许同一用户同时由
  legacy 和 Nakama 扣款。切回前停止 Nakama 写入口，等待 in-flight operation
  进入 committed/rejected，再恢复 legacy。
- `decks.save` 冲突只回滚本次 revision；保留上一版 canonical deck 和
  operation receipt。`cards.upgrade`/`chests.open` 失败不做客户端侧补偿，
  只能按 ledger 反向交易或人工审计。
- 出现掉落表 hash 不一致时立即禁用 `chests.open`，不回退到客户端随机。
- 已 committed 的 `chests.open` 不回滚掉落；若 UI 未收到响应，用原
  `idempotency_key` 查询 receipt。只有明确 rejected 且未改变 wallet/
  inventory 的 operation 才可安全重试。
- 回滚不删除 Nakama `asset_operations`、ledger 或 opening audit；这些记录
  是恢复/对账依据，敏感 seed 只保留 server-side hash/受限存储。

## 验收测试

### 服务端

- 读取接口只返回当前 user 的数据；篡改 user id、越权 collection key 和
  未认证请求均失败。
- `inventory.get` 返回 wallet、inventory revision 和 snapshot hash；伪造
  body `user_id` 不改变 owner，返回结果不泄露其他用户。
- `decks.save` 拒绝非法卡牌、重复卡、禁用卡、旧 revision，并返回稳定
  validation；重试相同幂等键只产生一次写入；响应 `deck_snapshot_hash`
  可被 `03` 直接复用。
- `cards.upgrade` 在余额不足、满级、卡牌不存在时不改变 wallet/inventory；
  并发升级不会双扣；相同 operation key 返回 duplicate receipt。
- `chests.list`/`chests.open` 使用服务端 pool version 和 server-side random
  seed，客户端只能看到 `seed_hash`/opening id；重复 operation 不重复发奖，
  `chest_openings`、ledger、inventory 三者可按 opening id 对账。
- Nakama runtime 重启/写冲突后可恢复；bootstrap 汇总与细分 RPC 的
  revision/hash 一致；所有 grant 都有审计记录且不含原始 seed/token。
- 最小本地命令（覆盖 core、Nakama dispatcher 和协议合同）：

  ```sh
  cd /root/gotouhou/Gensoulkyo
  go test ./runtime/core ./runtime/nakamaapi ./runtime/security
  go test -tags nakama ./cmd/gensoulkyo_nakama ./runtime/...
  ```

- Nakama/PostgreSQL conditional-write 验收：

  ```sh
  cd /root/gotouhou/Gensoulkyo/deployments/nakama
  ./build-plugin.sh
  docker-compose up -d
  docker-compose ps
  docker-compose exec postgres psql -U postgres -d nakama -c \
    "select count(*) from storage"
  ```

  随后用 Nakama `POST /v2/rpc/<rpc_id>?unwrap=true`（body double-encoded）
  调用 `inventory.get`、`decks.save`、`cards.upgrade`、`chests.list`、
  `chests.open`。用同一 `idempotency_key` 重放三个写 RPC，断言 wallet/
  inventory/deck/chest revision、ledger 和 opening 只变化一次；用第二个
  用户 token 访问第一个用户的 key 必须得到 owner 数据而非请求体数据。
- 协议门禁：

  ```sh
  python3 /root/gotouhou/docs/ops/protocol_audit_check.py
  ```

### 客户端

- Collection/Deck/Chest 页面能解析成功和业务错误，不把失败响应当作本地
  成功；重复点击只发同一幂等请求或安全复用 receipt。
- `fetchChests()` 的 Nakama 调用 id 必须是 `chests.list`；旧 fallback 的
  `chests.get` 不得泄漏到 Nakama RPC。
- 保存 deck 后显示服务端 canonical 顺序和 snapshot hash；匹配前使用该
  hash，不使用未保存的本地草稿；revision conflict 时先刷新再由用户确认。
- 开箱动画只消费 `results/grants`，不读 `server_seed`；断线重连后按
  operation/opening id 查询/恢复，不重新抽取。
- client build 的 HTTPS live check 覆盖空库存、revision conflict、版本过期、
  网络重试和重新登录后的数据恢复。
- 最小客户端命令：

  ```sh
  cd /root/gotouhou/SpellKard/laya
  npm run typecheck
  npm test
  ```

## 明确不在范围内

商店/Steam 交易、活动领取、赛季排名、战斗结算奖励、房间创建和 battle
ticket 不在本切片；这些功能必须通过本切片提供的 canonical asset/ledger
接口接入。

商店边界固定为：本切片只提供 wallet、inventory、catalog、ledger 这些
可被未来软货币商店消费的基础面；当前 Gensoulkyo 没有 `shop.list` 或
`shop.purchase` 自研实现，因此本轮不虚构迁移来源。真实货币、Steam
Inventory、商品价格和运营掉落策略仍属于 `07_steam_closed_layer`，不得由
`nakama-server-agent` 在本切片落地。

## 实现完成判定

服务端 agent 必须能用 opening/ledger/revision 三个维度解释每一次资产变化，
并证明客户端无法指定 owner、余额、掉落或最终等级。client agent 必须能在
断线重试后展示同一 canonical 响应，不重复播放奖励，不用本地草稿进入匹配。
