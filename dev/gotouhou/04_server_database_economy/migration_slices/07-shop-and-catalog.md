# 07 商店与商品（Shop / Catalog / Purchase）

## 目标和边界

新增 Nakama 侧的商店目录与购买能力。这是当前 Gensoulkyo **完全缺失**的模块
（仓库现有 `serverCardCatalog` 只是 12 张卡牌的静态数值表，没有 shop/product/
catalog/purchase 任何逻辑）。本切片负责：商品目录读取、购买扣费、发货、
幂等与账本。

**不在范围内**：宝箱随机掉落（属 `02`）、活动奖励发放（属 `06`）、
结算发奖（属 `05`）、客户端商店 UI 动画细节（属 client-agent）。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | authenticated `user_id`、`product_id`、`quantity`、幂等键、业务 envelope |
| 输出 | `ShopCatalogResponse`、`ShopPurchaseResponse`、wallet/inventory delta、`ShopReceipt` |
| 前置依赖 | `01` 身份、`02` economy ledger（钱包/库存）、卡牌稀有度表、宝箱池版本 |
| 下游使用者 | 客户端 Shop 页面、bootstrap 摘要 |
| 实现归属 | `nakama-server-agent`：catalog/purchase RPC、storage、扣费事务、幂等；`client-agent`：ShopScene + `shop.catalog`/`shop.purchase` 调用 |

## 当前 Gensoulkyo 的岗位

- **无**。`runtime/core` 中没有 shop/product/catalog/purchase 类型或函数。
- 可复用：`serverCardCatalog`（卡牌数值）、`serverCardRarities`（稀有度）、
  `ChestPool`/`ChestPityRules`（宝箱池与权重）、`WalletSnapshot`、
  `InventorySnapshot`、现有业务 envelope 幂等表模式。

## 目标 Nakama 契约

### 数据模型（`runtime/core/types.go` 新增）

```go
type ServerShopProduct struct {
    ProductID   string `json:"product_id"`    // "card.focus_lens.single"
    Kind        string `json:"kind"`          // "card" | "chest" | "currency_bundle"
    CostKind    string `json:"cost_kind"`     // "gold" | "gems"
    CostAmount  int    `json:"cost_amount"`
    Payload     string `json:"payload"`       // card_id 或 chest_pool_id
    Quantity    int    `json:"quantity"`
    Rarity      string `json:"rarity"`        // 来自 serverCardRarities
    Season      string `json:"season"`
    DailyLimit  int    `json:"daily_limit"`   // 0 = 无限制
    Purchasable bool   `json:"purchasable"`
}

type ShopCatalogResponse struct {
    Products []ServerShopProduct `json:"products"`
    Wallet   WalletSnapshot      `json:"wallet"`
    Season   string              `json:"season"`
    ServerTime int64             `json:"server_time"`
}

type ShopPurchaseRequest struct {
    ProductID string `json:"product_id"`
    Quantity  int    `json:"quantity"`
    Nonce     string `json:"nonce"`           // 幂等键
}

type ShopReceipt struct {
    ReceiptID  string `json:"receipt_id"`
    ProductID  string `json:"product_id"`
    Quantity   int    `json:"quantity"`
    CostKind   string `json:"cost_kind"`
    CostAmount int    `json:"cost_amount"`
    CreatedAt  int64  `json:"created_at"`
}

type ShopPurchaseResponse struct {
    OK       bool             `json:"ok"`
    Wallet   WalletSnapshot   `json:"wallet"`
    Granted  []GrantEntry     `json:"granted"`
    Receipt  ShopReceipt      `json:"receipt"`
    ServerTime int64          `json:"server_time"`
}
```

### RPC

| RPC | 输入 | 输出 | 错误码 |
| --- | --- | --- | --- |
| `shop.catalog` | 无业务字段（可选 `season`） | `ShopCatalogResponse` | `unauthorized`, `storage_unavailable` |
| `shop.purchase` | `product_id`、`quantity`、幂等键 | `ShopPurchaseResponse`、wallet/inventory delta | `product_not_found`, `not_purchasable`, `insufficient_currency`, `daily_limit_reached`, `idempotency_conflict`, `quantity_invalid` |

**服务端权威约束（强制）**：

1. 客户端**不得**提交价格、稀有度、掉落或奖励字段；`product_id` 只能引用目录中
   已存在的商品，`quantity` 受目录上限与 `daily_limit` 约束。
2. 扣费与发货必须在**同一事务**内：先校验余额 → 扣费 → 发货 → 写 ledger → 写 receipt。
3. 幂等键绑定 `user_id + product_id + quantity + request_hash`；相同请求重试
   返回原 receipt，**不得重复扣费**。
4. 目录由服务端静态配置驱动（`serverShopCatalog`），客户端只读。
5. 数量上限：单次购买 `quantity <= 10`（可配置），`daily_limit` 按
   `user_id + product_id + day` 计数。

### Storage（Nakama）

| collection | key | 内容 |
| --- | --- | --- |
| `shop_catalog` | `season` | 只读商品定义 + config version（服务端写入） |
| `player_purchases` | `user_id:receipt_id` | request hash、product、cost、grants、before/after revision |
| `player_purchase_limits` | `user_id:product_id:day` | 当日已购数量 |
| `economy_ledger` | `user_id:ledger_id` | debit/credit、reason=`shop_purchase`、idempotency key（复用 `02`） |

### 默认目录（`serverShopCatalog`，建议 6-8 项）

以现有 12 张卡为基础，覆盖 common/uncommon/rare/epic 各档：

| product_id | kind | cost | payload | 说明 |
| --- | --- | --- | --- | --- |
| `card.focus_lens.single` | card | 200 gold | focus_lens ×1 | common 单卡 |
| `card.bomb_amplifier.single` | card | 200 gold | bomb_amplifier ×1 | common 单卡 |
| `card.purge_charm.single` | card | 500 gold | purge_charm ×1 | uncommon 单卡 |
| `card.density_surge.single` | card | 1200 gold | density_surge ×1 | rare 单卡 |
| `card.last_arc.single` | card | 300 gems | last_arc ×1 | epic 单卡 |
| `chest.standard.pull` | chest | 800 gold | 标准池 ×1 | 复用 `ChestPool` |

价格档：common=200 gold、uncommon=500 gold、rare=1200 gold、epic=300 gems。

### HTTP 路由（`runtime/httpapi`）

新增 `GET /v1/shop/catalog`、`POST /v1/shop/purchase`，
与 RPC 共享同一 `core.Service` 方法（两入口一致）。

## 客户端接入点

- `lobby_client.ts` 新增 `fetchShopCatalog()` / `purchaseProduct(productID, quantity)`。
- `REST_ROUTES` 补 `shop.catalog` → `shop.catalog`、`shop.purchase` → `shop.purchase`。
- 新建 `shop_scene.ts`：商品网格（名称/稀有度/价格）、余额栏、
  购买确认弹窗、成功后按服务端 `granted` 刷新余额与库存。
- **禁止**客户端本地计算价格或掉落。

## 数据迁移与回滚

- 迁移：无历史商店数据，纯新增；wallet/inventory 沿用 `02` 的 storage。
- 回滚：移除 `shop.catalog`/`shop.purchase` 注册与路由即可；已购数据保留在
  `player_purchases` 不影响其它切片。

## 验收测试

服务端：

```bash
cd <worktree>/Gensoulkyo
go test -tags nakama ./runtime/... ./cmd/gensoulkyo_nakama
docker-compose --profile test run --rm test
python3 /root/gotouhou/docs/ops/protocol_audit_check.py
```

断言清单：

1. `shop.catalog` 返回目录，且 `purchasable` 与服务端配置一致。
2. 余额充足时购买：wallet 正确扣减、inventory 正确增加、返回 receipt。
3. 余额不足：`insufficient_currency`，**wallet 与 inventory 不变**。
4. 相同幂等键重试：返回同一 receipt，**wallet 只扣一次**。
5. 超过 `daily_limit`：`daily_limit_reached`。
6. 客户端提交伪造价格/数量上限：被忽略或 `quantity_invalid`。
7. `product_not_found` / `not_purchasable` 分支覆盖。

## 依赖

- 前置：`01`（身份）、`02`（wallet/inventory/ledger）。
- 可与 `03`/`06` 并行（不共享文件：新增独立 `runtime/core/shop.go`）。
- 协议：不需要新 protobuf，RPC 走既有 JSON 信封。
