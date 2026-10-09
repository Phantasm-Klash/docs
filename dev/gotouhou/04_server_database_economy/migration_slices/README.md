# Nakama 迁移切片规格

本目录存放把 Gensoulkyo 自研业务面迁移/对接 Nakama 的**可实现切片规格**，由
`nakama-migration-planner-agent` 输出，供 `nakama-server-agent` 与
`client-agent` 并行实现。

每个切片文件必须包含：

1. **范围**：本切片覆盖的 RPC / 场景，以及明确不在范围内的部分。
2. **目标契约**：RPC id、入参/出参 JSON 字段、storage collection/key、leaderboard id、错误码。
3. **客户端接入点**：客户端模块、方法名、UI 场景、传输选择。
4. **数据迁移**：从现有 Gensoulkyo 存储到 Nakama storage 的映射与回填方式。
5. **回滚策略**：如何在不破坏线上数据的前提下回退。
6. **验收测试**：最小可跑的验证命令与断言清单（服务端 + 客户端）。
7. **依赖**：前置切片、跨仓依赖、协议冻结要求。

命名：`<序号>-<主题>.md`，例如 `01-login-and-bootstrap.md`。

## 当前切片索引

| 切片 | 可独立实现的职责 | 主要依赖 |
| --- | --- | --- |
| `01-auth-and-bootstrap.md` | 账号、Nakama session、profile、bootstrap、版本门禁 | Nakama auth、业务 envelope |
| `02-inventory-decks-and-chests.md` | wallet、inventory、cards、decks、chests、economy ledger | `01`、卡池/ruleset |
| `03-matchmaking-rooms-and-lobby.md` | matchmaker、房间、规则快照、lobby WSS | `01`、`02` deck snapshot |
| `04-battle-allocation-and-ticket.md` | Battle Server registry、allocation、signed ticket | `03`、battle key |
| `05-settlement-and-replay.md` | signed result、幂等结算、Replay、结算 outbox | `03`、`04`、Battle Server |
| `06-activity-rewards-and-leaderboards.md` | task/event、leaderboard、claim、奖励 ledger | `02`、`05`、运营配置 |
| `07-shop-and-catalog.md` | 商店目录、购买扣费、发货、幂等 receipt、legacy HTTP/Nakama RPC 双传输 | `01`、`02` economy ledger |
| `08-mode-qualification-and-boss-state.md` | 模式资格、模式配置、考证 profile、世界/副本 Boss 业务状态 | `01`、`03`、`05`、PhK-Protocol |
| `09-admin-config-and-audit.md` | 运营配置、热更新、补偿、封禁与管理审计 | `01`、`02`、`05`、`06`、`08`、内网/VPN |

建议并行边界：`01` 完成身份契约后，`02` 与 `03` 可并行开发；
`04` 依赖 `03` 的 match roster；`05` 依赖 `04` 的 ticket/allocation；
`06` 可先实现读模型和 claim，待 `05` outbox 接通后启用结算进度写入；
`07` 可在 `02` 的 economy ledger 之后独立实现；`08` 可先实现 `modes.get`、
配置/资格读模型和迁移 shadow compare，但 `ValidateModeEntry` 要接入 `03`，
Boss HP/评级写入要等 `05` 的 verified settlement callback；`08` 不阻塞
Battle Server 的实时 mode action 实现。`09` 可先实现 admin storage、审批、
审计和 config preview；publish/compensation 的副作用分别等待 `08`/`02` 的
repository contract，玩家通知可与管理面并行。
