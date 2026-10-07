# 09 运营配置、补偿与管理审计

## 目标和边界

把 Gensoulkyo 当前散落在 Go 常量、内存状态和部署配置中的运营控制面拆到
Nakama/Go Runtime：版本化配置发布、活动/卡池/禁卡/奖励倍率/公告的热更新、
玩家封禁、补偿发放和管理审计。运营操作必须有独立的管理员身份、审批/二次
确认和不可变审计记录；玩家 session 不能调用本切片的写 RPC。

本切片覆盖：

- mode/card/chest/activity/reward/announcement 配置的 draft、preview、publish、
  rollback 和生效窗口；
- 禁卡/限卡、维护开关、玩家 sanction（ban/mute/queue block）；
- 面向明确用户集合的补偿 campaign、领取幂等和过期；
- 管理员操作、配置 diff、审批、失败原因和安全事件审计查询；
- 向玩家通过业务 WSS 推送只读的配置版本、公告和补偿可用通知。

明确不在范围内：

- 玩家账号登录、identity link、Steam 所有权和 session 生命周期；
- `02` 的钱包/库存 ledger 实现，`05` 的结算发奖，`06` 的活动进度与赛季榜；
- C++ Battle Server 实时状态、已开始 match 的 ruleset/seed/deck 快照；
- Steam Inventory、市场、支付风控和闭源商业服管理员控制台；
- 直接修改历史结算、排行榜分数、Boss HP、replay 或已消费 receipt。

热更新只影响尚未锁定的入口和新开的活动窗口。match 创建时已经锁定的
`ruleset_version`、`mode_config_hash`、`deck_snapshot_hash`、seed 和奖励规则
不得被运营发布覆盖。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 管理输入 | authenticated operator identity、作用域、config draft/release、reason、approval token、idempotency key |
| 玩家输入 | 仅 `compensation.claim` 的 claim intent；不得提交补偿内容、余额或封禁字段 |
| 输出 | `ConfigRelease`、preview diff、publish receipt、sanction receipt、compensation receipt、audit query page、只读 WSS notification |
| 前置依赖 | `01` identity/role mapping、`02` economy ledger、`05` settlement/outbox、`06` activity/event config、`08` mode config |
| 并行依赖 | PhK-Protocol 的业务 envelope/错误码；部署环境的内网/VPN、operator SSO 和密钥轮换 |
| 实现归属 | `nakama-server-agent`：admin RPC、storage、审批/条件写、配置快照和审计；`client-agent`：只读公告/补偿通知投影，不实现管理权限 |
| 输出消费者 | `03`/`08` 入口读取当前配置；`05`/`06` 消费锁定版本和补偿 ledger；玩家客户端消费通知 |

## 当前 Gensoulkyo 的岗位

代码对照以当前 `Gensoulkyo` core 和 migrations 为准：

- `runtime/core/types.go` / `service.go`
  - `ModeConfigs`、静态 card catalog/rarity/ban 表、`ChestPool`、默认
    task/event 和 world Boss 配置承担规则来源；
  - 用户内存状态保存 wallet、tasks/events、Boss snapshot 和 settlement
    projection，但没有 operator identity、release version 或审批状态；
  - `BusinessEvent`、battle/lobby lifecycle audit 和 settlement/replay audit
    记录运行时事件，不等于运营配置变更审计。
- `runtime/security`
  - business envelope guard 负责版本、seq、timestamp、nonce、op、key/tag、
    replay rejection 和脱敏 audit sink；
  - 该 guard 是公共安全基础，不授予 operator 权限，也不应被当作管理 RBAC。
- `runtime/nakamaapi/handler.go`
  - 已有业务 RPC/WSS adapter 与 `business.envelope.audit.status`、
    `battle.audit.status`、`lobby.audit.status` 诊断面；
  - 当前没有管理员专用 RPC、config release repository、sanction 或
    compensation campaign。
- `migrations/001_business_security_audit.*.sql`
  - 已有 envelope、battle、replay、lobby 审计表及 SQL sink；
  - 本切片新增运营审计/版本/补偿表，不能把管理员 payload 追加到玩家业务
    audit 表后再靠 endpoint 字段区分。
- `SpellKard`
  - `gensoulkyo_http_client.gd`、`game_mode_model.gd` 和 activity/result
    projection 已有配置、公告、补偿/奖励的玩家展示边界；
  - 客户端只能应用 server-authoritative 的版本和 grant，不提供管理员
    发布入口，不根据本地时间或本地配置解除封禁/领取限制。

## 目标 Nakama 契约

### 管理员 RPC

以下 RPC 只允许 operator service account 或具备明确 scope 的管理员 session。
Nakama handler 在业务 envelope 之外还必须校验 operator role、内网/VPN 来源、
租户/环境、审批 token 和二次确认 nonce；普通 Nakama user session 一律返回
`forbidden`，不得通过伪造 `user_id`、`owner_key` 或请求字段绕过。

| RPC | 输入 | 输出/副作用 | 最低 scope |
| --- | --- | --- | --- |
| `admin.config.preview` | `config_kind`、base version、draft payload/hash | normalized diff、validation errors、affected future entries | `config.read` |
| `admin.config.publish` | draft/release hash、expected active version、reason、approval token、confirm nonce | immutable `ConfigRelease`、publish receipt、audit event | `config.publish` + 高风险二次确认 |
| `admin.config.rollback` | config kind、target release、expected active version、reason、approval token | new rollback release；不删除历史版本 | `config.rollback` + 高风险二次确认 |
| `admin.sanction.set` | target user、sanction kind、starts/ends、reason、case id、confirm nonce | sanction receipt、effective version、audit event | `moderation.write` |
| `admin.compensation.issue` | campaign id、target selector/hash、grant template、expires at、reason、approval token | campaign receipt；实际资产仍由 `02` ledger 发放 | `compensation.write` + 二次确认 |
| `admin.audit.query` | time/cursor、actor/target/kind/status filters | redacted audit page and next cursor | `audit.read` |

管理员响应必须包含 `environment`、`config_kind`、`active_version`、
`source_hash`、`server_time`、`audit_event_id` 和 `server_authoritative=true`。
`publish`/`rollback` 不接受客户端直接提供的 `active_version` 作为覆盖值，
而是用 `expected_active_version` 做 compare-and-swap。

### 玩家 RPC/WSS

| RPC/事件 | 输入 | 输出/副作用 | 权限 |
| --- | --- | --- | --- |
| `compensation.get` | 可选 campaign id/cursor | 当前 user 可见的 campaign 摘要、expires_at、claim status | authenticated player |
| `compensation.claim` | campaign id、nonce、business envelope | `CompensationReceipt`；调用 `02` ledger 幂等发放 | authenticated player；只能使用 session user |
| `liveops.get` | known config versions/cursor | 公告、维护状态、可见 feature flags、config versions | authenticated player |
| WSS `liveops.updated` | server event | release id/kind、announcement summary、invalidated cache keys | authenticated player |
| WSS `compensation.available` | server event | campaign id、expires_at、display metadata | authenticated player |

WSS 通知是提示，不是资产或权限凭据。客户端必须随后调用
`compensation.get`/`liveops.get` 获取权威状态；重复通知不能重复发放。
不得注册 `admin.*` 为客户端可见 RPC，也不得让客户端提交 grant、target
selector、ban status、config payload 或 announcement priority。

### Storage collection/key

| collection | key | 内容 | 写入者 |
| --- | --- | --- | --- |
| `liveops_config_releases` | `config_kind:release_id` | normalized payload、source hash、parent release、effective window、status、actor/audit id | admin repository |
| `liveops_config_active` | `environment:config_kind` | active release id/version/hash、CAS revision、published at | admin repository |
| `liveops_config_drafts` | `environment:config_kind:draft_id` | draft payload/hash、validation result、expires at、owner scope | admin repository |
| `operator_roles` | `environment:operator_id` | scopes、tenant、mfa level、active/revoked at、role version | identity/admin provisioning |
| `operator_approvals` | `approval_id` | actor, operation digest, approver, expires at, consumed/revoked status | approval service |
| `player_sanctions` | `environment:user_id:sanction_id` | kind、start/end、reason code、case id、active/revoked, release/audit id | moderation repository |
| `compensation_campaigns` | `environment:campaign_id` | target selector hash, grant template id, window, cap, config version, status | admin repository |
| `compensation_claims` | `campaign_id:user_id` | claim status, ledger transaction id, nonce, claimed at, duplicate/rejected reason | `02` ledger bridge |
| `admin_audit_events` | `environment:event_id` | actor/role, operation, target, request digest, before/after hash, reason, result, trace id, created at | append-only audit sink |
| `liveops_outbox` | `environment:event_id` | notification type, payload hash, delivery attempts, delivered/expired | admin/runtime worker |

配置写入必须使用 storage version/conditional write；`publish` 只能从预期 active
版本推进一个新 release。历史 release 和 audit event append-only，rollback 是
指向旧 release 的新发布事件，不是删除或覆写旧行。`compensation_claims` 的
唯一键保证同一 campaign/user 只能产生一个成功 ledger transaction。

### 配置锁定与结果边界

`03`/`04`/`08` 在 match/room/allocation 创建时复制并锁定：
`mode_config_version`、`mode_config_hash`、`ruleset_version`、奖励模板版本和
禁卡列表版本。`admin.config.publish` 只改变 future read；`05` 结算使用
locked snapshot，不重新读取当前 liveops 配置计算旧 match 奖励。封禁从生效时
阻止新入口/新 claim，但不得中断已开始的 server-owned match；异常处置另由
battle result policy 标记，不由管理员 RPC 直接改结果。

### Leaderboard 面

本切片不写 authoritative leaderboard。管理员可读取 audit/配置影响范围，但
不能通过 config publish、compensation 或 sanction 修改 `rank_score`、
`single_score`、`world_boss_damage`。补偿资产通过 `02` ledger，赛季奖励通过
`06` claim/outbox，任何人工更正必须留下 adjustment transaction 和 case id。

## 客户端接入点

- `gensoulkyo_http_client.gd`
  - 增加 `liveops.get`、`compensation.get`、`compensation.claim` 的 Nakama
    HTTPS transport；所有写请求沿用业务 envelope 和 nonce；
  - 订阅业务 WSS 的 `liveops.updated`/`compensation.available`，通知只触发
    刷新，不直接改变 wallet、inventory、ban 或 mode entry。
- `gensoulkyo_api_model.gd`
  - 投射 `config_versions`、`maintenance`、announcement、campaign status 和
    compensation receipt；
  - 拒绝非 `server_authoritative`、旧 environment 或缺少 `audit/receipt`
    的响应。
- `game_mode_model.gd`、activity/reward model
  - 收到 config invalidation 后刷新 `08` mode snapshot 或 `06` activity
    snapshot；已锁定 match 继续使用本地保存的 server snapshot；
  - 补偿成功只接受 `02` 返回的 wallet/inventory delta，不本地合成 grant。
- 管理控制台不属于 SpellKard；如后续存在独立 operator UI，必须调用
  `admin.*` service endpoint，不能复用玩家客户端 token 或把 secret 放入
  Godot 资源。

## 数据迁移

1. 从 Gensoulkyo 导出当前 `ModeConfigs`、card/chest/task/event 静态配置、禁卡
   表、活动/公告状态、已有补偿和封禁记录，以及 envelope/battle/lobby audit
   的审计摘要。不得导出 session token、原始密钥、管理员密码或未脱敏设备
   标识。
2. 生成 canonical normalized payload 和 `source_snapshot_hash`；相同配置以
   `config_kind + source hash` 去重，不以 map iteration 顺序产生不同版本。
3. 先导入 `liveops_config_releases` 的 inactive 历史版本，再以 CAS 写入
   `liveops_config_active` 的 shadow version；`03`/`08` 在 shadow 阶段只比较
   hash，不使用迁移中的配置放行玩家入口。
4. 导入 operator role 时只迁移 identity link、scope 和 MFA 状态；无法唯一
   映射的管理员进入 `needs_review`，不得按 display name 猜测权限。
5. 导入 sanctions/compensation 时保留原 case/campaign id、时间窗口、原始
   status 和 source hash；已完成补偿映射到 `compensation_claims`，再与 `02`
   ledger transaction id 对账，不能重新发放。
6. 运行 `legacy` -> `shadow` -> `nakama` 水位切换。切换记录 migration
   batch、source watermark、active release、operator policy version 和
   cutover event；同一 config kind 只能有一个写权威。

## 回滚策略

- `liveops_authority` 支持 `legacy`、`shadow`、`nakama`，按 environment 和
  config kind 切换；shadow 不产生玩家资产或 sanction 副作用。
- 配置校验失败、审计 sink 不可用、审批过期或 CAS 冲突时拒绝 publish，继续
  使用旧 active release；不采用客户端默认配置。
- 发布后发现错误时执行 `admin.config.rollback` 生成新 release，指向最后一个
  已验证版本；不删除错误版本，已开始 match 和已发放 ledger 不回滚。
- compensation campaign 回滚只关闭未领取对象；已成功 claim 的 ledger
  transaction 保留，纠错使用新的 adjustment campaign，不重复扣/发资产。
- sanction 回滚必须是新的 revoke/shorten audit event；不能删除原 sanction
  记录。已开始对局不被强制改写，下一次入口/claim 再读取最新 sanction。
- Nakama storage 或 outbox 故障时关闭新 publish/claim，允许只读旧 snapshot；
  恢复后按 event id/claim key 重放。WSS 丢失只影响提示，不影响权威状态。

## 验收测试

### 服务端

- 普通玩家 session 调用任一 `admin.*` 返回 `forbidden`；缺 role、scope、
  内网/VPN、MFA、approval 或 confirm nonce 的高风险操作不产生配置/资产变化。
- `admin.config.preview` 对未知字段、非法窗口、破坏已锁定规则和错误 hash
  返回 validation errors；preview 不写 active release。
- 两个并发 publish 使用同一 `expected_active_version` 时只有一个 CAS 成功；
  rollback 产生新 release，历史 release/audit 仍可查询。
- match 已锁定的 ruleset/config 不受热更新影响；新入口读取新版本，旧 match
  结算按 locked snapshot 执行。
- compensation claim 对同一 campaign/user 的重试、重复 nonce、断线重连只
  产生一个 ledger transaction；过期、非目标用户和已封禁 claim 按固定错误码拒绝。
- sanction 只阻止新入口/新 claim，不直接改变进行中 match、rank、Boss HP 或
  replay；revoke 有独立 audit event。
- admin audit query 只返回脱敏 payload/hash、角色、scope、reason、结果和
  trace id；不返回 session token、私钥、原始设备标识或 grant secret。
- Nakama/PostgreSQL 重启后 active release、CAS revision、approval 消费状态、
  compensation claim、sanction 和 outbox 可恢复；重放不重复发布或发奖。
- 服务端最小检查：

  ```sh
  cd /root/gotouhou/Gensoulkyo
  go test ./runtime/core ./runtime/security ./runtime/nakamaapi ./runtime/httpapi
  ```

- Nakama/PostgreSQL 优先使用 `docker-compose`：

  ```sh
  cd /root/gotouhou/Gensoulkyo/deployments/nakama
  ./build-plugin.sh
  docker-compose up -d
  docker-compose ps
  ```

- 协议/网络/安全门禁：

  ```sh
  python3 /root/gotouhou/docs/ops/protocol_audit_check.py
  ```

### 客户端

- `liveops.get`/`compensation.get` 能解析版本、窗口、公告、campaign status；
  非 server-authoritative 或 environment/version 不匹配时进入可恢复刷新状态。
- `liveops.updated` 重复或乱序到达时只触发一次刷新；客户端不把通知当作
  grant、封禁解除或 mode entry 凭据。
- 合法 claim 成功后只按服务端 wallet/inventory delta 更新；重复 claim 显示
  already claimed/duplicate，不叠加本地数量；过期和无资格状态可展示原因。
- 收到配置 invalidation 后，新建房间读取新 config hash，已有 match 的页面
  保留锁定 snapshot；客户端不能通过重启绕过 sanction 或版本门禁。
- 相关 Godot 检查入口：

  ```sh
  cd /root/gotouhou/SpellKard/godot
  /root/gotouhou/Godot_v4.7-stable_linux.x86_64 --headless --path . --script ../tools/client_smoke_test.gd
  ```

## 明确不在范围内

`01` 负责 operator identity link 的来源，`02` 负责补偿实际 ledger，
`05` 负责已锁定结果的结算，`06` 负责活动进度/排行榜/赛季 claim，`08` 负责
模式配置读取和入口资格。`09` 不实现第二套经济账本、管理员 UI、战斗模拟或
客户端可写的运营配置。

## 实现完成判定

服务端 agent 能证明管理员发布、回滚、封禁、补偿和 audit query 均有独立权限、
审批、CAS/幂等和 append-only 审计路径；配置热更新不会改写已开始 match，
补偿不会绕过 `02` ledger。client agent 能通过只读 liveops/compensation
接口展示状态并处理乱序通知，而不能获得 admin scope 或自行改变权威状态。
