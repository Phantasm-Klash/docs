# 01 账号会话与 Bootstrap

## 目标和边界

把 Gensoulkyo 当前的匿名/外部账号映射、业务 session 和启动快照迁移到
Nakama 身份与 Go Runtime。这个切片是库存、卡组、匹配和活动切片的前置。
它只负责身份、会话、版本门禁和 bootstrap 聚合，不负责钱包写入、匹配、
奖励发放或 leaderboard 写入。

这是第二阶段迁移规格，不改变当前 MVP 的 keep/abandon 决策。迁移期间
`auth.anonymous` 仍可作为兼容 RPC，但新客户端应优先使用 Nakama 标准设备
认证。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | 设备标识（仅传哈希/opaque id）、display name、platform、client build、已知 `ruleset_version` |
| 输出 | Nakama `user_id`/session、稳定 `player_id`、profile、版本状态，以及 bootstrap 聚合快照 |
| 前置依赖 | Nakama/PostgreSQL、PhK-Protocol 版本、业务 envelope guard、经济/模式读取接口 |
| 下游切片 | `02-inventory-decks-and-chests`、`03-matchmaking-rooms-and-lobby`、`06-activity-rewards-and-leaderboards` |
| 实现归属 | `nakama-server-agent`：认证、RPC、storage、迁移脚本；`client-agent`：session 持久化和启动流程 |

## 可直接开工的交付边界

`nakama-server-agent` 只需要交付以下三组入口，其他切片不得重复实现身份
映射：

| 入口 | Nakama 面 | 输入类型 | 输出类型 | 成功副作用 |
| --- | --- | --- | --- | --- |
| 标准设备认证 | Nakama `authenticateDevice` | `device_id`、`create`、可选 display name | Nakama `Session` | 创建/恢复 Nakama user；写 `player_profile` |
| `auth.anonymous` | custom RPC，兼容迁移 | `AuthAnonymousRequest` | `AuthSession` 投影 | 幂等建立 `identity_link` 和 profile |
| `bootstrap` | authenticated custom RPC；可选 WSS `business.event` 只读通知 | `BootstrapRequest{KnownRulesetVersion}` | `BootstrapSnapshot` | 只读聚合；可选刷新 cache，不得发奖/扣费 |

当前可复用的代码边界是
`Gensoulkyo/runtime/core/service.go` 的 `LoginAnonymous`、`LoginExternal`、
`Bootstrap`，以及 `Gensoulkyo/runtime/nakamaapi/handler.go` 的 RPC 分发和
envelope 校验。实现完成后，HTTP fallback 仍可调用同一 core contract，但
Nakama RPC 必须成为主路径；不要在 `cmd/gensoulkyo_nakama` 重新复制业务规则。

## Nakama 面的精确约束

- 认证使用 Nakama session；`auth.anonymous` 不接受客户端传入 `user_id`、
  `player_id`、wallet、inventory、deck 或任何资产字段。
- `player_profile`、`identity_link` 是 Go Runtime 的可写 storage；
  `player_bootstrap_cache` 只能保存带 `schema_version`、`source_hash` 的可重建
  摘要。Nakama user id 是所有 collection 的 owner，客户端不得指定 owner。
- 本切片不调用 Nakama `leaderboard` 写 API。bootstrap 只读取 `06` 切片提供的
  leaderboard 摘要，读取失败时返回明确的 `read_source`/降级状态，不能伪造空
  排名。
- `business.event`/WSS 只传版本或 session 状态通知；不把 bootstrap 大快照
  当作高频广播，也不把 session token 放进通知 payload。

## 当前 Gensoulkyo 的岗位

- `LoginAnonymous` 创建用户、session token，以及默认 wallet、inventory、deck、
  chest、task、event、leaderboard、certification 数据。
- `LoginExternal` 把外部 Nakama user/session 映射到 core session。
- `Bootstrap` 以 core session 返回 `user_id`、`session_token`、`display_name`、
  `server_version`、`ruleset_version`、`modes`、`wallet`、`inventory`、
  `decks`、`chests`、`tasks`、`events`、`leaderboards`、`certification`、
  `world_boss`。
- Nakama HTTP adapter 用 `user_id` 派生稳定 core session；WSS 使用 Nakama
  session id。除登录外的调用要求业务 envelope。

## 目标 Nakama 契约

### 认证和 RPC

1. 首选 Nakama `authenticateDevice`（或平台认证适配器）创建/恢复 Nakama
   session。设备原始标识不得写入日志或业务 storage；只允许不可逆的
   `device_subject_hash` 用于迁移审计。
2. 迁移期保留 custom RPC `auth.anonymous`：

   ```json
   {
     "display_name": "Player",
     "platform": "self_hosted",
     "client_build": "client-build-id"
   }
   ```

   返回 `user_id`、`session_token`、`display_name`、`player_id`、
   `ruleset_version`、`server_version`。该 RPC 只允许创建/恢复当前身份，
   不接受客户端指定 `user_id` 或资产。
3. custom RPC `bootstrap` 只接受可选的
   `known_ruleset_version`，认证上下文决定用户：

   ```json
   { "known_ruleset_version": "ruleset-local-s0" }
   ```

   返回应保持现有 `BootstrapSnapshot` 形状，并增加：
   `session_expires_at`、`migration_mode`、`required_client_build`、
   `read_source`。版本不兼容时返回 `version_mismatch` 和更新所需版本，
   不返回可继续游戏的半旧快照。

### Storage

| collection | key | 内容 | 写入者 |
| --- | --- | --- | --- |
| `player_profile` | `user_id` | `player_id`、display name、platform、profile version、created/updated at | 认证 Runtime |
| `identity_link` | `user_id` | 旧 Gensoulkyo user id、外部 subject hash、迁移批次、映射状态 | 迁移工具/认证 Runtime |
| `player_bootstrap_cache` | `user_id` | 可重建的版本化读取摘要；不能作为钱包或奖励权威 | bootstrap Runtime（可选） |

Nakama session token、refresh token 和签名密钥不写入上述业务 collection。
`player_bootstrap_cache` 失效时必须从各业务 collection 重建。leaderboard
本切片不写入，只允许读取由 `06` 切片定义的公开摘要。

### 错误码和安全约束

统一返回 `invalid_request`、`unauthorized`、`identity_conflict`、
`version_mismatch`、`migration_not_ready`、`internal_error`。所有认证后的
custom RPC/WSS 继续验证 `protocol_version`、`seq`、`timestamp`、`nonce`、
`op` 和幂等/重放规则；登录 RPC 不携带业务 envelope，但仍受 Nakama
认证和速率限制保护。

## 客户端接入点

- `SpellKard/laya/src/core/net/lobby_client.ts`
  - 保留 `loginAnonymous()`，内部改为标准设备认证后调用兼容 bootstrap；
  - 保留 `bootstrap(knownRulesetVersion)`，补充 `migration_mode`、
    `required_client_build` 和 `version_mismatch` 处理；
  - session token、`user_id`、`player_id` 只存本地安全存储，不写普通日志。
- `SpellKard/laya/src/core/game/lobby_flow.ts`
  - `signIn()` 保持 login -> bootstrap 顺序；
  - bootstrap 失败或版本不匹配时停留在登录/更新状态，不进入 Lobby；
  - session 过期时清空本地业务状态并重新认证，不能复用旧 envelope seq。
- `lobby_protocol.ts` 的 bootstrap route 继续支持 HTTPS RPC；需要推送的
  profile/version 通知才使用 WSS。身份认证阶段不依赖自定义 `room_state`。

## 数据迁移和发布

1. 从旧 Gensoulkyo user state 导出 `legacy_user_id`、display name、
   platform 和创建时间；不导出 session token。
2. 按不可逆 subject hash 或受控人工映射写入 `identity_link`，以
   `user_id` 为 Nakama owner 建立 `player_profile`。重复映射必须停止批次，
   不能静默覆盖。
3. 先双读校验 profile：Nakama 缺失时读旧状态并写回；校验
   `player_id`、display name 和版本字段一致后，才切换 bootstrap 主读。
4. 迁移批次记录 `migration_batch_id`、源快照 hash、目标写入版本和校验
   时间。完成后冻结旧身份创建，仅保留只读回填窗口。

迁移批次最小记录固定为：
`migration_batch_id`、`legacy_user_id`、`nakama_user_id`、
`device_subject_hash`（可选）、`source_snapshot_hash`、
`target_profile_version`、`status`、`rejected_reason`、`checked_at`。
`status` 至少包含 `pending`、`shadow_match`、`active`、`orphan`、
`rejected`；批次脚本必须支持按 `legacy_user_id` 重跑而不覆盖已 active
映射。

## 回滚策略

- 以配置开关选择 `legacy`、`shadow`、`nakama` 三种 bootstrap source。
- `shadow` 只比较脱敏字段和 hash，不把 Nakama token 回写旧系统。
- 出现身份冲突、版本错误或 profile 丢失时，切回旧 bootstrap；已创建的
  `player_profile`/`identity_link` 标记为 orphan，禁止删除和复用。
- 不回滚 Nakama session；客户端重新认证即可。回滚后禁止在旧系统写入
  新的 Nakama-only `player_id`，除非映射已存在。

## 验收测试

### 服务端

- 新设备认证能得到稳定 `user_id`、`player_id`，重复认证不重复创建 profile。
- 同一 legacy identity 的重复导入被拒绝；两个 legacy identity 指向同一
  Nakama user 时返回 `identity_conflict`。
- `bootstrap` 返回完整快照和版本字段；已知 ruleset 相同与不同的响应分别
  命中缓存路径和 `version_mismatch`。
- 未认证、过期 session、伪造 user id、缺失/重放 envelope 均被拒绝。
- bootstrap 读取失败时不产生钱包、宝箱或奖励副作用；审计记录不含 token。
- 最小本地命令（Gensoulkyo）：

  ```sh
  cd /root/gotouhou/Gensoulkyo
  go test ./runtime/nakamaapi ./runtime/core ./cmd/gensoulkyo_nakama
  ```

- Nakama/PostgreSQL 集成命令（必须使用 `docker-compose`）：

  ```sh
  cd /root/gotouhou/Gensoulkyo/deployments/nakama
  ./build-plugin.sh
  docker-compose up -d
  docker-compose ps
  curl -fsS http://127.0.0.1:7350/healthcheck
  ```

- 协议/网络安全门禁：

  ```sh
  python3 /root/gotouhou/docs/ops/protocol_audit_check.py
  ```

- `go test -tags nakama ./cmd/gensoulkyo_nakama ./runtime/...` 和 plugin build
  必须在能访问 pinned Nakama SDK/pluginbuilder 的环境执行；失败时报告首个
  依赖错误，不把未构建 tag 当作通过。

### 客户端

- `LobbyFlow.signIn()` 成功路径依次完成认证和 bootstrap，显示服务端
  display name 后进入 Lobby。
- session 过期、版本不匹配、网络超时都停在可恢复状态，不能进入匹配。
- 刷新页面后恢复 session 时不重复提交旧 seq/nonce，退出登录会清空本地
  session 和 bootstrap 派生状态。
- 用 Nakama HTTPS endpoint 做 live check，验证返回字段可被
  `LobbyClient` 解析；不把 session token 打到 console。
- 最小客户端命令：

  ```sh
  cd /root/gotouhou/SpellKard/laya
  npm test
  ```

  Godot 入口若本切片触及共享登录投影，再追加：

  ```sh
  cd /root/gotouhou/SpellKard/godot
  /root/gotouhou/Godot_v4.7-stable_linux.x86_64 --headless --path . --script ../tools/client_smoke_test.gd
  ```

## 明确不在范围内

Steam 购买校验、社交关系、经济写操作、leaderboard 排名写入、房间状态、
battle ticket、Replay 和奖励结算由其他切片负责。
