# Nakama ↔ 客户端业务对接面（v0 现状与目标）

> 本文件由 gap 分析产出，作为 `nakama-server-agent` 与 `client-agent` 的**共同契约基线**。
> 权威代码：`Gensoulkyo`（Nakama Go runtime 插件）、`SpellKard/laya`（LayaAir 3 TS 客户端）。

## 0. 传输拓扑

| 场景 | 目标通道 | 认证 |
| --- | --- | --- |
| 登录 / 引导 / 仓库 / 卡牌 / 牌组 / 宝箱 / 商店 / 建房 / 匹配 | `POST /v2/rpc/<rpc_id>?unwrap=true` | Basic `:<http_key>` 或 `Bearer <session_token>` |
| 业务 WSS 通知 | `GET /ws`（Nakama socket）+ `rpc` 帧 | session token |
| 对战实时帧 | 直连 104 UDP 7400-7419（KCP）／Web 端经大厅 WS 中继 | battle ticket |

**关键约定**

- HTTP RPC body 是 **JSON 字符串**（double-encoded）：`"{\"seed\":1}"` 而非 `{"seed":1}`。
- `?unwrap=true` 时返回体直接是 payload，不含 `{payload:...}` 包装。
- 服务端返回统一结构：`{"ok":true, ...}` / `{"ok":false,"error_code":"..."}`。
- roster 用 `player_id`（`p-<shortHash>`），不是 `user_id`。
- `result_hash` 必须带 `sha256:` 前缀。

## 1. 现状缺口（gap）

| 能力 | 服务端 RPC | 客户端方法 | 状态 |
| --- | --- | --- | --- |
| 匿名登录 | `auth.anonymous` ✅ | `loginAnonymous` ✅ | 客户端走自研 `/v1/auth/anonymous`，**未接 Nakama** |
| 引导快照 | `bootstrap` ✅ | `bootstrap` ✅ | 同上 |
| 仓库 | `inventory.get` ✅ | ❌ 缺 | 待建 |
| 卡牌升级 | `cards.upgrade` ✅ | ❌ 缺 | 待建 |
| 牌组读写 | `decks.list` / `decks.save` ✅ | ❌ 缺 | 待建 |
| 宝箱 | `chests.list` / `chests.open` ✅ | ❌ 缺 | 待建 |
| 活动领取 | `activity.claim` ✅ | ❌ 缺 | 待建 |
| 商店/商品 | ❌ **服务端完全缺失** | ❌ 缺 | **需新建** |
| 房间列表/规则 | `rooms.list` / `rooms.rules` ✅ | ❌ 缺 | 待建 |
| 建房/加入 | `rooms.create` / `rooms.join` ✅ | `createRoom`/`joinRoom` ✅ | 路由未映射 |
| 匹配 | `matchmaking.join` / `.ticket` / `.cancel` ✅ | ✅ | 路由未映射 |
| 就绪/开局 | `match.ready` ✅ | `readyMatch` ✅ | 路由未映射 |
| 战报/结果 | `replay.get` / `battle.result.submit` ✅ | `fetchReplay` ✅ | 路由未映射 |

## 2. 客户端网络层改造（模块 A）

`src/core/net/lobby_client.ts` 当前 `REST_ROUTES` 只映射 13 条自研 `/v1/...` 路径，未知 id 回退 `POST /v1/rpc/{id}`。

**目标**：

1. 新增 `NakamaLobbyTransport`，实现 `POST /v2/rpc/<rpc_id>?unwrap=true`：
   - `http_key` 走 Basic auth（用户名是 http_key 值，密码空）。
   - 有 session 后改用 `Authorization: Bearer <session_token>`。
   - body 做 double-encode。
2. `REST_ROUTES` 补齐下表映射（id → Nakama RPC id 直通）。
3. 保留 `HttpLobbyTransport`（自研 `/v1/...`）作为回退，由 `app.ts` 按 config 选择。

### 2.1 REST_ROUTES 目标映射表

| 客户端 id | Nakama RPC id | 方法 | 说明 |
| --- | --- | --- | --- |
| `auth.anonymous` | `auth.anonymous` | POST | 入参 `{device_id, display_name?}` |
| `bootstrap` | `bootstrap` | POST | 返回 wallet+inventory+decks+chests+tasks+events+leaderboards+certification+world_boss |
| `inventory` | `inventory.get` | POST | `InventorySnapshot` |
| `cards.upgrade` | `cards.upgrade` | POST | `{card_id, target_level}` → `CardUpgradeResponse` |
| `decks` | `decks.list` | POST | `DeckListResponse` |
| `decks.save` | `decks.save` | POST | `SaveDeckRequest` → `SaveDeckResponse{validation}` |
| `chests` | `chests.list` | POST | `ChestSnapshot` |
| `chests.open` | `chests.open` | POST | `ChestOpenRequest` → `ChestOpenResponse` |
| `shop.catalog` | `shop.catalog` | POST | **新建** |
| `shop.purchase` | `shop.purchase` | POST | **新建** |
| `activity.claim` | `activity.claim` | POST | 返回 wallet 增量 |
| `rooms` | `rooms.list` | POST | 房间列表 |
| `rooms.rules` | `rooms.rules` | POST | `{mode}` → 规则集 |
| `rooms.create` | `rooms.create` | POST | |
| `rooms.join` | `rooms.join` | POST | |
| `rooms.leave` | `rooms.leave` | POST | |
| `matchmaking.join` | `matchmaking.join` | POST | |
| `matchmaking.ticket` | `matchmaking.ticket` | POST | |
| `matchmaking.cancel` | `matchmaking.cancel` | POST | |
| `match.ready` | `match.ready` | POST | |
| `battle.allocation` | `battle.allocation` | POST | |
| `battle.ticket` | `battle.ticket` | POST | |
| `replay.get` | `replay.get` | POST | |

## 3. 服务端新建模块（模块 E：商店/商品）

当前 `serverCardCatalog`（12 张卡）与 `serverCardRarities` 只是**静态数值表**，没有商店/商品/购买逻辑。

**目标实现（在 `runtime/core` 内）**：

```
ServerShopProduct {  // 静态商品定义
  product_id     string   // "card.focus_lens.bundle1"
  kind           string   // "card" | "chest" | "currency_bundle"
  cost_kind      string   // "gold" | "gems"
  cost_amount    int
  payload        string   // card_id 或 chest_pool_id
  quantity       int
  rarity         string
  season         string
  daily_limit    int
  purchasable    bool
}

ShopPurchaseRequest  { product_id string; quantity int; nonce string }
ShopPurchaseResponse { ok bool; wallet WalletSnapshot; granted []GrantEntry; receipt ShopReceipt }
ShopReceipt          { receipt_id string; product_id string; cost WalletDelta; created_at int64 }
ShopCatalogResponse  { products []ServerShopProduct; wallet WalletSnapshot; season string }
```

**约束**：

- 扣费必须在同一事务内，购买幂等（`nonce` 去重，复用 `business` 幂等表模式）。
- 服务端权威：客户端不得提交价格或数量上限。
- 复用 `ChestPityRules` / `ChestPool` 的 weights 模式处理卡片包。
- 新增 RPC `shop.catalog` / `shop.purchase`，同步补 `nakamaapi` + `httpapi` 两条路由。

## 4. 客户端 UI 场景（模块 B-F）

`src/platform/laya/scenes/` 当前只有 4 个场景：`lobby_scene` / `room_scene` / `battle_scene` / `result_scene`。

**待建场景**：

| 场景 | 数据源 | 关键交互 |
| --- | --- | --- |
| `inventory_scene` | `inventory.get` | 道具列表、数量、稀有度 |
| `card_scene` | `inventory.get` + `cards.upgrade` | 卡牌升级（显示 cost / max_level） |
| `deck_scene` | `decks.list` / `decks.save` | 牌组编辑保存、校验反馈 |
| `chest_scene` | `chests.list` / `chests.open` | 宝箱开启动画、pity 显示 |
| `shop_scene` | `shop.catalog` / `shop.purchase` | 商品列表、购买确认、余额显示 |

**大厅改造**：`lobby_scene.ts` 现用 `PRESET_ROOM_CODES=['RACE01',...]` 循环，应改为 `Laya.TextInput` 文本输入 + `rooms.list` 列表选房。

## 5. 验收测试清单

服务端（每个切片）：

```bash
cd /root/gotouhou/Gensoulkyo
go test ./runtime/... ./cmd/gensoulkyo_nakama
docker-compose --profile test run --rm test
python3 /root/gotouhou/docs/ops/protocol_audit_check.py
```

客户端（每个切片）：

```bash
cd <worktree>/SpellKard/laya
npm run typecheck
npm test          # 期望 0 failed
```

端到端（新增 RPC 后）：

```bash
python3 tools/e2e_remote_agent_smoke.py
```

## 6. 并行分工建议

| 模块 | Owner | 依赖 |
| --- | --- | --- |
| A 网络层切换 | `client-agent` | 无（可先做，回退保留） |
| B 登录/引导对齐 | `client-agent` | A |
| C 道具/仓库 + 卡牌 | `nakama-server-agent`(校验契约) + `client-agent` | A |
| D 牌组 | `client-agent` | A |
| E 商店（服务端新建） | `nakama-server-agent` | 无 |
| E 商店（客户端） | `client-agent` | A, E 服务端 |
| F 建房/房间列表 | `client-agent` | A |
