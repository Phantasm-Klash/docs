# 07 商店目录、购买与账本迁移切片

## 目标和边界

把 Gensoulkyo 当前的内存商品目录和购买逻辑迁移为 Nakama/Go Runtime
的服务端权威商品目录、扣款、发货、幂等 receipt 和经济账本。完成标准
是：Nakama 主面、旧 HTTP fallback 和客户端最终显示同一套 server-owned
商品、价格、grant、钱包和 receipt。

本切片覆盖：

- 商品目录读取和固定 `catalog_version`；
- `product_id`/`quantity`/`nonce` 购买意图校验；
- wallet 扣减、card/chest/currency grant、receipt、ledger 和条件写；
- 旧内存 `ShopPurchased`/`ShopInventory` 与新 product API 的迁移对账；
- LayaAir Nakama/HTTP 双传输、幂等重试和回滚开关。

明确不在范围：

- 卡牌定义、卡牌升级、宝箱随机掉落和 pity（`02`）；
- 活动/签到奖励（`06`）；
- 战斗结算发奖（`05`）；
- Steam Inventory、真实货币、市场交易和闭源商品配置；
- 商店 leaderboard。购买不产生排名，本切片不注册或写入 Nakama
  leaderboard。

## 输入、输出与依赖

| 项目 | 规格 |
| --- | --- |
| Nakama 输入 | authenticated `ctx.UserID`、`product_id`、正整数 `quantity`、业务幂等 `nonce`、可选 `catalog_version`、business envelope |
| legacy 输入 | 旧 HTTP `item_id`、`count`；无可依赖的幂等 receipt，只能保留为受限 fallback |
| Nakama 输出 | `ShopCatalogResponse`、`ShopPurchaseResponse`、嵌套 `ShopReceipt`、`GrantEntry`、canonical wallet/inventory、ledger/operation id |
| `nakama-server-agent` 输入 | `01` 的 Nakama owner、`02` 的 `player_wallet`/`player_inventory`/`economy_ledger` contract、当前目录 seed |
| `nakama-server-agent` 输出 | `shop.catalog`/`shop.purchase` RPC、catalog storage、atomic purchase write、legacy importer、authority switch |
| `client-agent` 输入 | Nakama HTTPS RPC endpoint、HTTP fallback、商品/receipt JSON contract |
| `client-agent` 输出 | `LobbyClient` 商品/购买 projection、稳定 nonce、Shop scene 错误/重试状态和 live check |
| 前置依赖 | `01-auth-and-bootstrap` 的 owner/session；`02-inventory-decks-and-chests` 的 asset revision、wallet、inventory、ledger 条件写 |
| 可并行 | 可与 `03`、`06` 并行；不得写入对方的 room/match/reward/leaderboard collection |
| 下游 | Collection/Shop 页面读取 canonical wallet/inventory；bootstrap 只聚合摘要，不复制购买权威 |

购买请求中客户端不得提交或影响 `cost_kind`、`cost_amount`、grant、wallet、
inventory、stock、rarity、server seed、receipt、ledger、user/owner id。服务端
只接受商品选择和数量。

## 当前 Gensoulkyo 的岗位

### 两套现状必须分开

当前仓库同时保留了新 product API 和旧 item API，迁移时不能把它们描述成
同一份数据：

1. `Gensoulkyo/runtime/core/shop.go`
   - `ShopCatalog(sessionToken)` 返回 `ShopCatalogResponse`；
   - `PurchaseShopProduct(sessionToken, ShopPurchaseRequest)` 接受
     `product_id`、`quantity`、`nonce`，在进程锁内扣钱包并发货；
   - `serverShopCatalog` 当前有 6 个商品；
   - `Service.shopPurchases` 按 `user_id + nonce` 保存 request hash 和原响应，
     `shopPurchaseLimits` 保存按日计数；
   - receipt 当前嵌套在 `ShopPurchaseResponse.receipt`，尚无持久化
     `economy_ledger`、`ledger_id` 或重启恢复。
2. `Gensoulkyo/runtime/core/service.go` 的 legacy `Shop`/
   `PurchaseShopItem`
   - `GET /v1/shop` 返回 `ShopView{currency,wallet,items}`；
   - `POST /v1/shop/purchase` 在 body 是 `item_id/count` 时走旧路径；
   - 旧 `ShopPurchased`/`ShopInventory` 仍是 user memory state，没有 receipt
     和条件写；
   - 旧路径的 `count <= 0` 兼容归一为 1，不能作为 Nakama 主写规则。

### 当前路由和 adapter

- `Gensoulkyo/runtime/nakamaapi/handler.go` 已登记
  `shop.catalog`、`shop.purchase`；authenticated Nakama RPC 通过
  `requestBody` 解包业务 envelope 后调用新 product API。
- `Gensoulkyo/runtime/httpapi/handler.go` 已提供
  `GET /v1/shop/catalog`、`POST /v1/shop/purchase`。purchase handler
  根据 `product_id/quantity/nonce` 或 `item_id/count` 选择新/旧 contract；
  该路由切换窗口只能有一个写 authority。
- `SpellKard/laya/src/core/net/lobby_client.ts` 当前仍以 `shop.get`、
  `item_id/count` 解析旧 `ShopView`/`ShopPurchaseView`；这不是 Nakama 主路径，
  client-agent 必须新增 `shop.catalog` product decoder，同时保留旧 alias
  作为 fallback。

### 必须保留的行为不变量

1. 商品 id、价格货币、金额、stock、rarity 和 grant 只来自当前服务端
   `shop_catalog`；客户端伪造价格/grant 必须拒绝或忽略。
2. wallet、inventory、purchase receipt、ledger 和 asset revision 必须在同一
   购买 operation 内提交；不能出现扣款成功而发货/receipt 缺失。
3. 同一 user、同一 `nonce`、同一请求 hash 的重试只返回原 receipt，不重复扣款；
   相同 nonce 用于不同 product/quantity 返回 `idempotency_conflict`。
4. 业务 envelope 的 transport nonce 与购买 `nonce` 是两个字段；网络重试复用
   购买 nonce，不能拿 envelope nonce 作为业务 receipt key。
5. 目录切换不改变已提交 receipt；过期 catalog 只能按发布策略完成或返回
   `catalog_version_mismatch`。
6. 购买结果中的 wallet/inventory 必须是提交后的 canonical projection；
   客户端本地预扣、计算价格或本地发货不算成功。
7. 商店只走业务 HTTPS RPC；WSS 只能推送已经提交的 read-only
   `economy.updated`，不接受购买写入。

## 目标 Nakama 契约

### RPC、传输和输入类型

Nakama 主路径使用 `POST /v2/rpc/<rpc_id>?unwrap=true`，body 是
double-encoded JSON string。owner 从 `ctx.UserID` 取得，不接受 request 中的
`user_id`/`player_id`。legacy `/v1/shop` 只在迁移 fallback 开关打开时可读；
legacy purchase 关闭后必须返回明确的 `migration_read_only`。

| RPC id | 传输 | 请求 | 响应/副作用 |
| --- | --- | --- | --- |
| `shop.catalog` | Nakama HTTPS RPC；HTTP mirror `GET /v1/shop/catalog` | `ShopCatalogRequest{catalog_version?}`，默认 `{}` | `ShopCatalogResponse`；只读目录/wallet，不写 ledger |
| `shop.purchase` | Nakama HTTPS RPC；HTTP mirror `POST /v1/shop/purchase` | `ShopPurchaseRequest{product_id,quantity,nonce,catalog_version?}` | `ShopPurchaseResponse`；原子扣费、发货、receipt、ledger |

Nakama authenticated RPC 的 envelope `op` 必须分别为 `shop.catalog` 和
`shop.purchase`，并检查 `version`、`seq`、`timestamp_ms`、`nonce`、`key_id`、
`tag`、`mode` 和 body hash。登录/匿名认证不在本切片重复定义。

`quantity` 固定为 `1..10`；`0`、负数和 `11` 以上返回
`quantity_invalid`。`catalog_version` 在读取时可只作客户端提示；购买时
若非空必须等于当前可购买目录版本。`nonce` 不能为空，长度和字符集按
业务 envelope 同等的 opaque id 规则校验，但不得在日志中输出原值。

### 输入/输出字段

目标 Go/JSON 对照：

```text
ShopCatalogRequest = {
  catalog_version?: string
}

ShopCatalogResponse = {
  ok: bool,
  products: ServerShopProduct[],
  wallet: map<string,int>,
  season: string,
  catalog_version: string,
  catalog_hash: "sha256:<hex>",
  server_time: int64,
  read_source: "nakama" | "legacy" | "shadow",
  server_authoritative: true
}

ServerShopProduct = {
  product_id: string,
  kind: "card" | "chest" | "currency_bundle",
  cost_kind: string,
  cost_amount: int,
  payload: string,
  quantity: int,
  rarity?: string,
  season: string,
  daily_limit: int,
  purchasable: bool
}

ShopPurchaseRequest = {
  product_id: string,
  quantity: int,
  nonce: string,
  catalog_version?: string
}

ShopPurchaseResponse = {
  ok: bool,
  wallet: map<string,int>,
  inventory: InventorySnapshot,
  granted: GrantEntry[],
  receipt: {
    receipt_id: string,
    product_id: string,
    quantity: int,
    cost_kind: string,
    cost_amount: int,
    catalog_version: string,
    ledger_id: string,
    created_at: int64
  },
  duplicate: bool,
  operation_id: string,
  server_authoritative: true,
  server_time: int64
}
```

当前 core 的 `ShopCatalogResponse` 尚无 `catalog_version`/`catalog_hash`/
`read_source`，`ShopPurchaseResponse` 尚无 `duplicate`/`operation_id`/
`ledger_id`；server agent 必须在 Nakama adapter/storage contract 中补齐这些
迁移字段，不得让 client-agent 猜字段或把旧 `ShopPurchaseView` 当作新响应。

统一错误码：

- `unauthorized`：没有有效 Nakama session；
- `invalid_request`：JSON 结构或必填字段缺失；
- `product_not_found`：`product_id` 不在目录；
- `not_purchasable`：商品存在但当前不可购买；
- `quantity_invalid`：数量不在 `1..10`；
- `catalog_version_mismatch`：购买基于过期/未知目录；
- `insufficient_currency`：目标 `cost_kind` 余额不足；
- `daily_limit_reached`：目录声明限购且已超过；
- `idempotency_conflict`：同 nonce 对应不同 request hash；
- `storage_conflict`：wallet/inventory 条件写冲突，可安全重读；
- `storage_unavailable`：Nakama storage/数据库不可用；
- `migration_read_only`：legacy 写入已关闭。

### 当前目录冻结

迁移第一批以 `shop-local-s0` 为版本，目录 hash 由规范化的产品 JSON 计算。
以下六项必须完整导入；不可用旧三项 legacy 商品替代：

| product_id | kind | cost | payload/quantity | rarity | daily_limit |
| --- | --- | --- | --- | --- | ---: |
| `card.focus_lens.single` | `card` | `gold:200` | `focus_lens / 1` | `common` | `0` |
| `card.bomb_amplifier.single` | `card` | `gold:200` | `bomb_amplifier / 1` | `common` | `0` |
| `card.purge_charm.single` | `card` | `gold:500` | `purge_charm / 1` | `uncommon` | `0` |
| `card.density_surge.single` | `card` | `gold:1200` | `density_surge / 1` | `rare` | `0` |
| `card.last_arc.single` | `card` | `gems:300` | `last_arc / 1` | `epic` | `0` |
| `chest.standard.pull` | `chest` | `gold:800` | `local_basic / 1` | empty | `0` |

`name`/`description` 等展示字段可由客户端本地化，但不能成为扣款依据。
`currency_bundle` 保留为 schema 类型，本目录暂不 seed。`daily_limit=0`
表示无限制；若未来增加周期限购，必须添加明确的 `period_id` 和 reset job，
不能复用 legacy lifetime `purchased` 计数。

### Nakama storage、ledger 和 leaderboard 面

`02` 的 wallet/inventory/asset revision 是资产权威；本切片新增目录、购买
receipt 和历史 collection：

| collection | key | 内容 | 写入者 |
| --- | --- | --- | --- |
| `shop_catalog` | `<catalog_version>` | products、catalog hash、season、生效时间、publish status | server/admin；玩家只读 |
| `shop_purchase_receipts` | `nonce`（owner=`ctx.UserID`） | request hash、product/quantity、catalog version、cost、grant、receipt/ledger/operation id、before/after revision、status | `shop.purchase` Runtime |
| `shop_purchase_history` | `receipt_id` | 完整可审计 receipt、source、created_at、migration batch | `shop.purchase`/importer |
| `player_wallet` | `primary` | 复用 `02`；扣款后 currencies/revision/hash | `shop.purchase` atomic batch |
| `player_inventory` | `primary` | 复用 `02`；card/chest/item grant 后 snapshot/revision/hash | `shop.purchase` atomic batch |
| `economy_ledger` | `ledger_id` | 复用 `02`；`reason=shop_purchase`、debit、grant、receipt、request hash | `shop.purchase` atomic batch |
| `asset_operations` | `operation_id`/request hash | 复用 `02`；canonical response、duplicate/status | `shop.purchase` |

玩家 collection 的 Nakama `owner_id` 必须来自 `ctx.UserID`，权限为
`permission_read=0`、`permission_write=0`。不能仅以
`user_id:nonce` 作为 owner-scoped key 的全局唯一保证；若同一用户并发购买，
receipt create-only/conditional write 必须先占住 nonce，再以 `02` 的
`player_asset_revision` 做统一水位。

一次成功购买的写集合必须包含 wallet、inventory、receipt、history、ledger、
asset operation 和新 revision；PostgreSQL repository 使用同一事务，Nakama
Runtime 使用等价的 conditional/batch write。只写 receipt 再异步扣费是非法
实现。

leaderboard 面为空集：不注册 leaderboard id、不调用
`nk.LeaderboardRecordWrite`，不从购买金额派生赛季分数。运营统计另开
admin-only projection。

## 客户端接入点

### LayaAir 方法与场景

- `SpellKard/laya/src/core/net/lobby_client.ts`
  - 保留 `fetchShop()`/`purchaseShopItem()` 作为上层兼容名，但内部目标
    operation 改为 `shop.catalog`/`shop.purchase`；
  - Nakama decoder 读取 `products`、`catalog_version`、nested `receipt`、
    `granted`、`duplicate`、`operation_id` 和 canonical InventorySnapshot；
  - 旧 `ShopView`/`ShopPurchaseView` decoder 只绑定 legacy
    `/v1/shop` fallback，不能用于 Nakama response；
  - 购买第一次点击生成稳定业务 nonce，超时/断线重试复用同一 nonce；
    重新开始一个新购买意图才生成新 nonce；
  - 不把 cost/grant/wallet/receipt 从本地 payload 回填到成功状态。
- `SpellKard/laya/src/core/game/lobby_flow.ts`
  - `openShop()` 先调用 `shop.catalog`；
  - 成功后以服务端 wallet/inventory 替换本地 snapshot；
  - `catalog_version_mismatch` 先刷新目录，不能自动换 nonce 重买；
  - `storage_conflict`/网络超时先用原 nonce 查询/重试，不能把未知状态当失败
    后再次扣费。
- `SpellKard/laya/src/platform/laya/scenes/shop_scene.ts`
  - 展示 product id、kind、cost、quantity、rarity、purchasable、wallet；
  - 成功提示使用服务端 `granted`/`receipt`；不本地抽卡、不本地计算价格；
  - `insufficient_currency`、`daily_limit_reached`、`migration_read_only`
    停留在 Shop 并显示服务端错误。
- `SpellKard/laya/docs/checkin_shop_contract.md`
  - 增加 `shop.catalog` Nakama body/response；
  - 把旧 `shop.get`/`item_id/count` 明确标为 legacy only；
  - 记录 `nonce` 与 envelope nonce 的区别、双传输切换和 receipt 恢复规则。

商店不使用战斗 transport。若 WSS 推送 `economy.updated`，payload 只能包含
`operation_id`、asset revision 和 lookup hint；客户端仍必须调用
`shop.catalog`/`inventory.get` 获取 canonical 状态。

## 数据迁移

### 输入和输出

迁移工具输入为不含 session token、原始设备 id 或密钥的用户 manifest：

```text
legacy_user_id
identity_link -> nakama_user_id
wallet
legacy ShopPurchased[item_id]
legacy ShopInventory[item_id]
new product purchase records (when still present in memory/export)
source_state_hash
source_exported_at
```

输出至少为：

```text
migration_batch_id
target_user_id
target_wallet_revision
target_inventory_revision
source_state_hash
target_state_hash
legacy_summary_receipt_ids
status
rejected_reason?
migrated_at
```

### 映射与顺序

1. 先按 `01` 的 `identity_link` 映射 user；一对多、冲突或缺失映射不切主读。
2. 写入/校验 `02` 的 wallet 和 inventory，再导入 catalog version。不能把
   legacy item 名称模糊映射为新 product id。
3. 新 product API 的 card grant 映射为 card inventory；chest grant 映射为
   owned chest pool；currency grant 映射为 wallet。card copies 不能误合并
   为 chest/item 数量。
4. legacy `ShopInventory` 的 `stamina_potion`、`gacha_ticket`、
   `card_dust` 只作为 `player_inventory.items` 的 legacy item namespace；
   不伪造为新 `card.*` product purchase。
5. legacy `ShopPurchased` 没有 receipt/ledger/request hash 时只写
   `shop_purchase_history` 的 `source=legacy_import` summary，不能制造假的
   committed purchase receipt。当前新 product receipt 只在内存
   `shopPurchases` 中存在；没有可靠 export 的历史同样只能记录
   `reconciliation_required`。
6. 每个 wallet/inventory/receipt/history/ledger import 写同一
   `migration_batch_id`、source/target hash 和 target revision。导入重跑使用
   `source_import:<batch_id>:<legacy_operation_id>` operation key，不能重复
   扣款或发货。
7. 先 `legacy`/`shadow` 双读比较 wallet、card/chest/item quantities、目录 hash
   和 target hash；一致后切 `nakama`。切换窗口禁止同一用户同时走两条 purchase
   写路径。

迁移状态至少包含 `pending`、`shadow_match`、`active`、
`reconciliation_required`、`rejected`、`orphan`。`ShopPurchased` 当前不是
按自然月重置，导入必须保留 lifetime summary，不得推断周期限购。

## 回滚策略

- `shop_authority=legacy|shadow|nakama` 控制 read/write；`shadow` 只比较
  catalog/wallet/inventory/result hash，不执行第二次购买。
- 切到 Nakama 前关闭 legacy purchase 写入，等待 in-flight 请求成为
  committed/rejected；同一 user 只允许一个 purchase authority。
- Nakama 购买成功后切回 legacy 时，不得按旧 item/count 重放已成功 product
  receipt；先按 nonce/receipt/ledger 对账，未知状态只能用原 nonce 查询。
- 目录 hash、wallet/inventory revision、ledger 或 receipt 不一致时关闭
  `shop.purchase`，保留 catalog/inventory 只读；不得退回客户端价格/发货。
- 回滚不删除 `shop_catalog`、receipt/history、asset operation 或 ledger。
  恢复 Nakama 时以已提交 receipt/ledger 和 asset revision 继续。

## 验收测试

### 服务端最小命令

```bash
cd /root/gotouhou/Gensoulkyo
go test ./runtime/core ./runtime/httpapi ./runtime/nakamaapi ./runtime/security ./cmd/gensoulkyo_nakama
go test -tags nakama ./cmd/gensoulkyo_nakama
```

Nakama/数据库联调必须使用 `docker-compose`：

```bash
cd /root/gotouhou/Gensoulkyo/deployments/nakama
./build-plugin.sh
docker-compose up -d
docker-compose ps
curl -fsS http://127.0.0.1:7350/healthcheck
```

协议/网络安全门禁：

```bash
python3 /root/gotouhou/docs/ops/protocol_audit_check.py
```

若 tag build/pluginbuilder 因 pinned Nakama SDK 或网络不可用失败，报告首个
依赖错误；无 tag 测试不能替代真实 plugin 验收。

### 服务端断言清单

1. `shop.catalog` 和 `/v1/shop/catalog` 返回相同 6 个 product id、价格、
   payload/quantity、rarity、season 和 catalog hash；Nakama 不注册 `shop.get`。
2. 伪造 cost/grant/wallet/owner 字段不会影响结果；缺失 session、非法 product、
   `quantity=0/11`、空 nonce、过期 catalog 分别返回指定错误且不变更资产。
3. 有效购买在一次 atomic operation 中扣正确 currency、发正确 card/chest/
   currency grant，并写 receipt、history、ledger、asset operation；结果包含
   nested receipt、operation id 和 canonical wallet/inventory。
4. 相同 user/product/quantity/nonce 重试只返回同一 receipt，`duplicate=true`
   或等价标记，wallet 只扣一次；同 nonce 不同 request hash 返回
   `idempotency_conflict`。
5. 并发购买最多一个 operation 占用相同 nonce；条件写冲突不产生半笔扣款或
   半笔发货，客户端可用原 nonce 安全重试。
6. Nakama/数据库重启后 catalog、wallet、inventory、receipt、ledger、asset
   revision 可恢复；不依赖 `Service.shopPurchases`/`shopPurchaseLimits`。
7. legacy `/v1/shop` 在 read-only fallback 下仍能读旧形状；关闭 legacy write
   后旧 purchase 返回 `migration_read_only`，不会绕过新 authority。
8. 本切片不调用 leaderboard write；购买响应不包含战斗结算/排名权威字段。
9. 伪造 user id、越权 storage key、重放 business envelope 和玩家 WSS purchase
   均失败。

### 客户端断言清单

1. Nakama transport 调用 `shop.catalog`/`shop.purchase`，HTTP fallback 调用
   `/v1/shop/catalog`/`/v1/shop/purchase`；legacy `shop.get` 只在显式旧配置下
   使用。
2. Shop 页面显示服务端 products/cost/grants，不根据本地价格或随机数判断成功。
3. 网络超时、断线和重复点击沿用同一 nonce；恢复后展示同一 receipt，不出现
   二次扣款/二次发货。
4. `catalog_version_mismatch`、`storage_conflict`、`insufficient_currency`、
   `migration_read_only` 均可恢复且停留在 Shop；失败不更新成功状态。
5. 刷新/重连/重新登录后按 operation id、receipt 或 catalog/inventory RPC
   恢复；本地修改 wallet/product/stock 不影响下一次服务端结果。
6. Laya live check 覆盖 6 商品读取、成功购买、未知 product、余额不足、数量
   边界、幂等重试和 legacy read-only fallback。

最小客户端命令：

```bash
cd /root/gotouhou/SpellKard/laya
npm run typecheck
npm test
```

## 交付物与完成判定

`nakama-server-agent` 必须交付：`shop.catalog`/`shop.purchase` RPC、目录
seed/hash、storage schema、wallet/inventory/ledger atomic write、receipt/
idempotency、legacy importer、authority switch、Nakama/HTTP tests。

`client-agent` 必须交付：Nakama/HTTP 双传输 decoder、稳定 nonce、product/
receipt projection、错误/重试状态、Shop UI 和 live check。

只有在 Nakama 主路径通过 6 商品与原子账本断言、legacy fallback 不会绕过
authority、重试不会重复扣款/发货、客户端不接受伪造价格/grant，并通过协议
审计后，本切片才算完成。
