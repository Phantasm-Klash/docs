# 07 商店目录、购买与账本迁移切片

## 目标和边界

把 Gensoulkyo 当前内存商城迁移为 Nakama/Go Runtime 的只读商品目录和
服务端权威购买写入。完成标准是：同一商品定义、价格、发货、钱包扣减和
幂等 receipt 在 Nakama RPC、旧 HTTP fallback 和客户端投影中保持一致。

本切片覆盖：

- 商品目录读取；
- 购买意图校验、扣款、发货、ledger 和 receipt；
- 迁移已有用户的钱包、商城已购次数和商城赠品；
- LayaAir 客户端的 RPC/HTTP 传输切换；
- 购买幂等、并发写冲突和回滚开关。

本切片不覆盖：

- 宝箱随机掉落和 pity（`02-inventory-decks-and-chests.md`）；
- 活动/签到奖励（`06-activity-rewards-and-leaderboards.md`）；
- 战斗结算发奖（`05-settlement-and-replay.md`）；
- Steam 商品、真实货币、市场交易和闭源运营配置；
- 商店 leaderboard。商店购买不改变排名；本切片**不创建、不写入**
  Nakama leaderboard。

## 当前实现审计

### Gensoulkyo 当前岗位

当前实现位于 `Gensoulkyo/runtime/core/service.go` 和
`runtime/httpapi/handler.go`：

- `Service.Shop(sessionToken)` 从静态 `shopItemCatalog()` 返回目录、钱包、
  `ShopPurchased` 计数和 `purchasable`；
- `Service.PurchaseShopItem(sessionToken, ShopPurchaseRequest)` 在进程内锁下
  校验商品、扣 `user.Wallet`，增加 `user.ShopInventory` 并增加
  `user.ShopPurchased`；
- `GET /v1/shop` 调用 `Shop`；
- `POST /v1/shop/purchase` 调用 `PurchaseShopItem`；
- 当前商品固定为 `stamina_potion`（300 gold，发放 1）、
  `gacha_ticket`（500 gold，发放 1）和
  `card_dust_bundle`（200 gold，发放 50 `card_dust`），均为无限库存
  (`stock = -1`)；
- 当前 `ShopPurchased` 和 `ShopInventory` 属于用户内存状态，没有独立
  purchase receipt、economy ledger、条件写入版本或重启后恢复保证；
- 当前请求没有幂等键。`count <= 0` 会被服务端归一化为 1，且当前没有
  单次数量上限；Nakama 目标必须改为显式拒绝非法数量，避免重试/边界输入
  产生歧义；
- 现有客户端操作名是 `shop.get` / `shop.purchase`，不是
  `shop.catalog`。迁移期保留这两个操作名，避免客户端同时发生命名和传输
  变更；
- 现有客户端 HTTP 合同为 `GET /v1/shop` 和
  `POST /v1/shop/purchase`。旧 HTTP fallback 在切换窗口继续保留，但不能
  与 Nakama 同时成为同一用户的写权威。

### 必须保留的行为不变量

1. 商品 id、价格货币、价格金额和发放物只能由服务端目录决定；客户端提交的
   价格、grant、库存和余额字段必须忽略或拒绝。
2. 钱包扣减、商品发放、ledger 和 receipt 必须以同一幂等购买为单位提交；
   任一部分失败都不能留下半笔购买。
3. 相同用户、相同 `idempotency_key` 和相同请求 hash 的重试只返回原 receipt，
   不得再次扣款或发货；相同 key 但请求 hash 不同必须返回
   `idempotency_conflict`。
4. 购买结果中的 wallet/inventory 是服务端提交后的完整投影；客户端不能把
   本地预扣或本地库存当作成功依据。
5. 目录版本在购买请求和 receipt 中固定；目录切换不改变已提交 receipt，
   旧版本商品只允许按发布策略继续完成或明确返回
   `catalog_version_mismatch`。
6. 商店操作不进入 battle transport、不产生 leaderboard 分数，也不直接
   调用 Steam/商业库存。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | Nakama authenticated `user_id`、`item_id`、正整数 `count`、`catalog_version`（购买时）、business envelope、`idempotency_key` |
| 输出 | `ShopView`/目录快照；`ShopPurchaseView` 加 `receipt_id`、`ledger_id`、`catalog_version`、完整 wallet/inventory |
| 当前输入兼容 | 旧 HTTP body `{ "item_id": "...", "count": 1 }`；旧 HTTP 继续由 fallback 接收，Nakama RPC 使用 envelope body |
| 前置依赖 | `01-auth-and-bootstrap` 的 Nakama user/identity；`02-inventory-decks-and-chests` 的 wallet、inventory、economy ledger conditional write |
| 可并行依赖 | 可与 `03-matchmaking-rooms-and-lobby`、`06-activity-rewards-and-leaderboards` 并行；不得改写对方的 match/reward/leaderboard collection |
| 实现归属 | `nakama-server-agent`：RPC、storage、事务/幂等、目录发布和迁移工具；`client-agent`：Laya lobby/shop 投影和错误/重试状态 |
| 下游输出 | Collection/Shop 页面使用 canonical wallet/inventory；bootstrap 只读摘要，不复制购买权威状态 |

## 目标 Nakama 契约

### RPC、传输和输入类型

保留已有客户端操作名，并在 Nakama Runtime 注册为 authenticated client
RPC：

| RPC id | 传输 | 输入 | 输出 | 说明 |
| --- | --- | --- | --- | --- |
| `shop.get` | Nakama HTTPS RPC；旧 HTTP `GET /v1/shop` 为迁移 fallback | `{}`；可选 `catalog_version` 仅用于读取提示 | `ShopView` + `catalog_version`、`server_time_ms`、`server_authoritative`、`read_source` | 只读，不写 ledger |
| `shop.purchase` | Nakama HTTPS RPC；旧 HTTP `POST /v1/shop/purchase` 为迁移 fallback | `item_id`、`count`、`catalog_version`、`idempotency_key` | `ShopPurchaseView` + receipt/ledger/revision 字段 | 只接受购买意图；价格和 grant 从目录重算 |

Nakama authenticated RPC 的业务 envelope `op` 必须分别为 `shop.get` 和
`shop.purchase`，并沿用 `protocol_version`、`seq`、`timestamp`、`nonce`、
`key_id`、`tag` 和 replay guard。登录/匿名认证不在本切片重新定义。

`count` 的目标边界为 `1..10`；超出范围返回 `quantity_invalid`。客户端当前
默认发送 `1`，所以不会影响正常调用。旧 HTTP fallback 可在迁移窗口保留
`count <= 0` 到 `1` 的兼容行为，但 Nakama 主写路径和切换后的 HTTP 路由
必须使用严格边界，并在审计中记录拒绝原因。

### 输入/输出字段

读取响应保持现有字段，增加迁移字段：

```json
{
  "ok": true,
  "server_authoritative": true,
  "currency": "gold",
  "wallet": { "gold": 700, "ticket": 1 },
  "items": [
    {
      "item_id": "stamina_potion",
      "name": "Stamina Potion",
      "description": "Restores one ranked attempt.",
      "price": { "gold": 300 },
      "grants": { "item": "stamina_potion", "count": 1 },
      "stock": -1,
      "purchased": 0,
      "purchasable": true
    }
  ],
  "catalog_version": "shop-local-s0",
  "server_time_ms": 0,
  "read_source": "nakama"
}
```

购买请求：

```json
{
  "item_id": "stamina_potion",
  "count": 1,
  "catalog_version": "shop-local-s0",
  "idempotency_key": "client-generated-opaque-key"
}
```

购买成功响应至少包含：

```json
{
  "ok": true,
  "server_authoritative": true,
  "item_id": "stamina_potion",
  "count": 1,
  "spent": { "gold": 300 },
  "wallet": { "gold": 400 },
  "inventory": { "stamina_potion": 1 },
  "receipt_id": "receipt-id",
  "ledger_id": "ledger-id",
  "catalog_version": "shop-local-s0",
  "duplicate": false,
  "server_time_ms": 0
}
```

同一幂等请求重试时返回相同 `receipt_id`、`ledger_id`、`spent`、wallet 和
inventory，并将 `duplicate` 置为 `true`；不得重新执行扣款。

统一错误码：

- `unauthorized`：没有有效 Nakama session；
- `not_found` / `product_not_found`：商品 id 不在服务端目录；
- `invalid_request`：缺少 item 或幂等键、非法结构；
- `quantity_invalid`：`count` 不在 `1..10`；
- `catalog_version_mismatch`：购买基于过期目录；
- `insufficient_funds`：余额不足；
- `out_of_stock`：有限库存耗尽；
- `idempotency_conflict`：幂等键复用于不同请求；
- `storage_conflict`：wallet/inventory 条件写冲突，客户端可安全重读后重试；
- `storage_unavailable`：持久化不可用。

### Nakama storage、索引和 leaderboard 面

`02` 已定义的 wallet/inventory/ledger collection 是资产权威；本切片新增
购买和目录 collection：

| collection | key | 内容 | 写入者 |
| --- | --- | --- | --- |
| `shop_catalog` | `catalog_version` | 商品定义、价格、grant、stock、可购买状态、配置 hash | 发布/管理员；客户端只读 |
| `shop_purchase_receipts` | `user_id:idempotency_key` | request hash、item/count、catalog version、spent、grant、receipt/ledger id、before/after revision、created_at | `shop.purchase` Runtime |
| `shop_purchase_history` | `user_id:receipt_id` | 可审计的完整 receipt；用于按 receipt 查询和迁移对账 | `shop.purchase` Runtime |
| `player_wallet` | `user_id` | 复用 `02`：扣款后的 currencies/revision/updated_at | `shop.purchase` 事务 |
| `player_inventory` | `user_id` | 复用 `02`：发放后的 item/card quantities/revision/updated_at | `shop.purchase` 事务 |
| `economy_ledger` | `user_id:ledger_id` | 复用 `02`：`reason=shop_purchase`、debit、grant、request hash、receipt id | `shop.purchase` 事务 |

Nakama storage 的写入必须使用 version/conditional write；若部署使用
PostgreSQL repository，则 wallet、inventory、receipt、history 和 ledger
需要同一数据库事务或等价的 outbox/补偿协议。不能只写
`shop_purchase_receipts` 再异步扣钱包。

本切片的 leaderboard 面是空集：不注册 leaderboard id，不调用
`nk.LeaderboardRecordWrite`，不从购买金额派生排名字段。若运营将来需要
购买统计，只能另建 admin-only analytics projection，不能复用赛季排名。

### 初始目录快照

迁移第一批必须按当前代码生成 `shop-local-s0`，不得采用旧规格中未实现的
稀有度、宝箱商品或 gems 价格：

| item_id | price | grants | stock | 迁移说明 |
| --- | --- | --- | --- | --- |
| `stamina_potion` | `gold: 300` | `stamina_potion: 1` | `-1` | 保留现有商品 |
| `gacha_ticket` | `gold: 500` | `gacha_ticket: 1` | `-1` | 保留现有商品 |
| `card_dust_bundle` | `gold: 200` | `card_dust: 50` | `-1` | 保留现有商品 |

`name`、`description` 是展示元数据，不能成为扣费依据。目录 hash 和
`catalog_version` 必须随发布 artifact 固定；目录配置变更产生新版本。

## 客户端接入点

目标客户端接入当前已存在的 LayaAir 业务层：

- `SpellKard/laya/src/core/net/lobby_client.ts`
  - 保留 `fetchShop()` 和 `purchaseShopItem(itemId, count)`；
  - `shop.get` / `shop.purchase` 的 Nakama RPC route 与 HTTP fallback 共用
    同一解码器；
  - 购买请求生成并复用 `idempotency_key`，重试不能生成新的 key；
  - 解析 `receipt_id`、`ledger_id`、`duplicate`、`catalog_version`；
  - 失败只更新 `lastError`，不能把本地预扣显示为成功。
- `SpellKard/laya/src/core/game/lobby_flow.ts`
  - `openShop()` 进入页面先读 `shop.get`；
  - `purchaseItem()` 成功后以服务端 wallet/inventory 替换本地快照；
  - `storage_conflict`、`catalog_version_mismatch` 先重读目录/库存，再由用户
    决定是否重新购买；不能自动以新幂等键重复扣款。
- `SpellKard/laya/src/platform/laya/scenes/shop_scene.ts`
  - 继续渲染 item/name/price/stock/purchased；
  - 购买按钮的可用状态只能参考服务端 `purchasable`；
  - 成功提示使用服务端 grant/receipt，不在客户端抽样或计算价格。
- `SpellKard/laya/docs/checkin_shop_contract.md`
  - 保留旧 HTTP wire shape 作为 fallback 兼容说明；
  - 补充 Nakama RPC 的 `catalog_version`、`idempotency_key` 和 receipt 字段；
  - 明确 Nakama 主路径的 envelope 和 `count=1..10` 边界。

商店只使用 Nakama HTTPS RPC。WSS 不承担购买写入；若将来推送余额变化，
只能发送服务端已提交的 `economy.updated` 只读通知，客户端仍需按 receipt
重读 canonical snapshot。

## 数据迁移

### 输入和输出

迁移工具输入为旧 Gensoulkyo 用户导出（不包含 session token 或原始密钥）：

```text
legacy_user_id
identity_link -> nakama_user_id
wallet
shop_purchased[item_id]
shop_inventory[item_id]
source_state_hash
```

输出为 `migration_batch_id`、`target_user_id`、`target_wallet_revision`、
`target_inventory_revision`、`source_state_hash`、`target_state_hash`、
`migrated_at` 和 per-user status。

### 顺序和映射

1. 先按 `01-auth-and-bootstrap.md` 的 `identity_link` 映射
   `legacy_user_id` 到 Nakama `user_id`；重复或一对多映射停止该用户。
2. 从当前 canonical wallet 导入/校验 gold 和其他货币；不得把
   `ShopInventory` 的赠品错误地合并为 card copies。
3. 将 `ShopInventory` 中的通用物品映射到 `player_inventory.items`：
   `stamina_potion`、`gacha_ticket`、`card_dust` 必须作为 item quantity，
   与 `02` 的 card inventory 分区保持可区分。
4. 将 `ShopPurchased` 映射到 `shop_purchase_history` 的 legacy summary。
   当前旧实现没有 receipt、ledger 和每笔购买 hash，因此不能伪造历史
   receipt；写入 `source=legacy_import`、源快照 hash 和总计数。
5. 写入 `player_wallet`/`player_inventory` 后重新计算 target hash，再写
   `migration_batch_id` 和状态。任一数量、货币或 item id 不一致时置为
   `rejected`，不切主读。
6. 迁移期间使用 `legacy`、`shadow`、`nakama` 三态读源；切换前禁止两边
   同时接受同一用户购买写入。

当前代码的 `ShopPurchased` 并未按自然月重置；迁移必须按 lifetime count
保留现状。若产品确实需要周期限购，应在新目录/数据模型中增加明确的
`period_id` 和 reset job，另开规格，不得把旧 `purchased` 字段误解释为
周期计数。

## 回滚策略

- 开关 `shop_authority=legacy|shadow|nakama` 控制读和写入口；
  `shadow` 只比较脱敏的目录 hash、wallet hash、inventory hash 和结果 hash，
  不执行第二次扣费。
- 切换到 Nakama 前停止旧 HTTP purchase 写入，等待旧请求完成或明确拒绝；
  同一用户只允许一个写权威。
- Nakama 失败时可切回 legacy 读路径，但不能把已经成功的 Nakama receipt
  在 legacy 重放。回滚前按 `idempotency_key`/receipt 对账，未完成事务只能
  由 Nakama 重试或人工补偿。
- 目录 hash 不一致、ledger 与 wallet 不一致或 receipt 缺失时立即关闭
  `shop.purchase`，保留 `shop.get` 只读；不能回退到客户端价格/发货。
- 回滚不删除 Nakama collection。`shop_purchase_receipts`、
  `shop_purchase_history` 和 `economy_ledger` 作为审计保留；恢复 Nakama
  时以 receipt/ledger 对账结果继续。

## 验收测试

### 服务端最小命令

在 Gensoulkyo 仓库执行：

```bash
cd /root/gotouhou/Gensoulkyo
go test ./runtime/core ./runtime/httpapi ./runtime/nakamaapi ./cmd/gensoulkyo_nakama
go test -tags nakama ./cmd/gensoulkyo_nakama
docker-compose --profile test run --rm test
python3 /root/gotouhou/docs/ops/protocol_audit_check.py
```

`go test -tags nakama` 若因 Nakama SDK 缓存/依赖不可用失败，必须在 Nakama
Compose 或联网 CI 中重跑；不能用无 tag 测试替代真实 plugin 构建。协议审计
是必需项，因为本切片新增 authenticated RPC、业务 envelope 和客户端可写
边界。

### 服务端断言清单

1. `shop.get` 和 HTTP fallback 返回三项初始目录，价格/grant/stock 与
   `shop-local-s0` 完全一致；客户端提交伪造价格不会改变响应。
2. 有效购买只扣服务端 wallet、增加对应 item、写一条
   `economy_ledger` 和一条 receipt；wallet/inventory/ledger/receipt 的
   revision 和 hash 可对账。
3. 余额不足、未知商品、`count=0`、`count=11`、过期目录版本和缺失幂等键
   分别返回指定错误，且 wallet、inventory、ledger 均不变化。
4. 相同 `idempotency_key` 和 request hash 重试返回同一 receipt，wallet
   只扣一次；相同 key 的不同 item/count 返回 `idempotency_conflict`。
5. 并发购买在 conditional write/数据库事务下最多成功一次对应扣款；
   storage conflict 可安全重读，不能产生半笔发货。
6. Nakama instance 重启后 receipt、wallet、inventory 和购买历史可恢复；
   `shop.get` 不依赖进程内 `ShopPurchased`/`ShopInventory`。
7. 服务端未调用 leaderboard 写入；购买结果不包含排名/战斗结算权威字段。
8. 伪造 `user_id`、未认证 session、重放 envelope 和玩家 WSS 写入均失败。

### 客户端断言清单

1. `fetchShop()` 能从 Nakama RPC 和旧 HTTP fallback 解码同一商品投影；
   页面显示服务端 price/grants，不计算本地价格。
2. 正常购买后使用服务端 receipt、wallet 和 inventory 刷新页面；失败响应
   不更新本地成功状态。
3. 网络超时重试沿用同一 `idempotency_key`，重复响应显示 duplicate 或同一
   receipt，不出现二次扣费。
4. `catalog_version_mismatch`、`storage_conflict`、`insufficient_funds`
   可恢复显示并停留在 Shop；不会跳转到战斗或伪造发货。
5. 刷新/重连后按 receipt 或 `shop.get` 恢复状态；客户端本地修改钱包、
   stock、purchased 不影响下一次请求。
6. 运行 LayaAir live check，覆盖目录读取、成功购买、未知商品、余额不足、
   幂等重试和重新登录后的状态恢复。

## 交付物和完成判定

`nakama-server-agent` 交付：Nakama RPC 注册、catalog seed、storage schema/
migration、conditional purchase transaction、receipt/ledger、legacy import
工具、authority switch 和 Go/Nakama tests。

`client-agent` 交付：`LobbyClient` 的 Nakama/HTTP 双传输投影、稳定幂等键、
Shop UI 错误状态、receipt 展示和 Laya live check。

切片只有在 Nakama 主路径通过服务端断言、客户端能切换传输且 legacy 回滚
不会重复扣款时才算完成。
