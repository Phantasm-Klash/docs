# 04 战斗服分配与 Battle Ticket

## 目标和边界

把 match roster 到 C++ Battle Server 的分配、容量心跳、一次性签名
`battle_ticket` 和消费审计迁移到 Nakama Go Runtime。Nakama 负责分配与票据
权威，C++ 只负责验证票据并运行高频战斗；本切片不负责战斗 tick、结果结算
或奖励。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | `match_id`、锁定 roster/deck snapshot、mode/ruleset hash、Battle Server register/heartbeat |
| 输出 | `BattleServerAllocation`、`SignedBattleTicket`、consume/reject audit |
| 前置依赖 | `01` 身份、`02` deck snapshot、`03` match roster、PhK battle schema、服务间 mTLS/密钥 |
| 下游切片 | `05-settlement-and-replay` 接收 signed result；C++ Battle Server 接收 ticket |
| 实现归属 | `nakama-server-agent`：server registry、allocation、签票、服务回调；battle-server-agent：消费/握手；`client-agent`：票据获取和 battle 连接 |

## 当前 Gensoulkyo 的岗位

- `battle.servers.register/heartbeat/offline` 维护 Battle Server 容量和健康；
  `battle.servers` 返回服务端列表。
- `battle.allocation` 按 match 分配 endpoint、server seed、player roster、
  mode config hash。
- `battle.ticket` 签发绑定 user/player、match、deck snapshot、规则版本、
  server id、endpoint、过期时间和一次性 nonce 的 Ed25519 ticket。
- `battle.ticket.consume` 由战斗服务验证/消费；`battle.agent.assignments`
  给进程 agent 查询活动 match。客户端不能调用服务专用注册、消费或提交
  伪造 allocation。

## 目标 Nakama 契约

### 客户端 RPC

| RPC | 输入 | 输出 | 权限 |
| --- | --- | --- | --- |
| `battle.allocation` | `match_id` | endpoint、server id、seed hex、players、version/hash | authenticated player，仅限 roster |
| `battle.ticket` | `match_id` | `SignedBattleTicket` | authenticated player，仅返回自己的 ticket |

### 服务端 RPC

| RPC | 输入 | 输出 | 权限 |
| --- | --- | --- | --- |
| `battle.servers.register` | server id、endpoint、region、build、capacity/load、supported modes | registry record | service origin + mTLS |
| `battle.servers.heartbeat` | 同上 | updated health | service origin + mTLS |
| `battle.servers.offline` | server id/status | retired status | service origin + mTLS |
| `battle.agent.assignments` | server id | active assignments | battle agent service identity |
| `battle.ticket.consume` | ticket id、match/user/player/server、nonce、hash | consumed/rejected result | C++ Battle Server service identity |

服务端响应必须包含 `protocol_version`、`business_api_version`、
`battle_api_version`、`ruleset_version`、`mode_config_hash`。Ticket 绑定
`deck_snapshot_hash`、`battle_server_id`、`expires_at`、唯一 nonce 和 key id；
默认 TTL 沿用当前 60 秒配置。消费是一次性的，过期/重复/错 match 均拒绝。

### Storage/状态面

| collection | key | 内容 |
| --- | --- | --- |
| `battle_servers` | `battle_server_id` | endpoint、region、build、capacity、active matches、load、supported modes、last seen |
| `battle_allocations` | `match_id` | server、endpoint、seed hash、roster、version/hash、status |
| `battle_tickets` | `ticket_id` | match/user/player、nonce hash、key id、issued/expires/consumed/revoked、status |
| `battle_ticket_audit` | `ticket_id:event_id` | issue/consume/reject reason、request hash、service identity |
| `battle_keys` | `key_id` | 公钥和 active/revoked metadata；私钥仅在受控签名服务/secret store |

leaderboard 不写入；allocation 的 server load 不是玩家成绩。禁止把私钥、
原始 token、完整 secret 或可用于伪造票据的签名材料写入 Nakama storage
或普通日志。

## 客户端接入点

- `lobby_client.ts` 保留 `fetchBattleAllocation(matchId)`、
  `fetchBattleTicket(matchId)`；解析 `ticket.ticket`、`signature_alg`、
  `key_id`、`signature_hex` 和 expiry。
- `lobby_flow.ts` 在收到 `match_start`/ready 后先获取 allocation，再取 ticket；
  只有 ticket 未过期、match id 与当前 roster 一致才进入 Battle。
- LayaAir Battle transport 使用 endpoint 和 opaque signed ticket 做
  ECDHE/KCP/UDP 握手；客户端不生成 server seed、player id、ticket nonce，
  也不调用 service-only RPC。
- 断线重连可重新读同一未消费 ticket；不能创建第二张可并行消费票据。

## 数据迁移

1. 只迁移健康 Battle Server registry 和仍有效的 active allocation；历史
   server heartbeat 作为 audit 导入，不作为可调度实例。
2. 对现有 active match 重新验证 roster、deck snapshot、ruleset 和 server
   capacity；无法验证的 allocation 标记 `migration_rejected`，不签新票。
3. 迁移旧 ticket 时只保存脱敏 ticket metadata 和签名 key id；已消费/过期
   ticket 不能恢复为可消费状态。必要时给 active match 重新签发新 ticket，
   新 ticket id 与旧 id 建立 replacement 链。
4. 切换前做 allocation shadow compare，确认同一 match 只会选择一个 server
   和一个 server seed；写入 batch/hash 供 `05` 结算对账。

## 回滚策略

- `battle_authority` 支持 `legacy`、`shadow`、`nakama`；任何时刻只有一个
  签票 authority 和一个 active signing key。
- Nakama 分配或签票故障时，停止新 match，允许未开始 match 过期；不要在旧
  系统直接复用 Nakama ticket。已消费票据不得回滚成可消费。
- key rotation 失败时保留旧公钥验证窗口，撤销新 key；泄漏/错配时立即
  revoke key 并让所有未消费 ticket 失效，记录 incident id。

## 验收测试

### 服务端和 Battle Server

- registry heartbeat 超时的 server 不可被新 allocation 选中；容量/模式/
  region 约束有效。
- 同一 match 的 allocation 幂等且 roster/hash 稳定；无 roster 的 user 无法
  读取 allocation/ticket。
- ticket 签名、key id、nonce、expiry、match/player/server/hash 绑定可验证；
  修改任一字段都拒绝。
- consume 首次成功、重复 consume、过期、错 server、错 nonce、错 match、
  revoked key 分别得到稳定结果；重复请求不启动第二个 battle session。
- service-only RPC 拒绝客户端 Nakama session、缺失 mTLS/origin 或业务 envelope
  混用；audit 不记录私钥和原始 token。
- 使用 `docker-compose` 启动 Nakama/PostgreSQL/Battle Server stub，运行
  battle ticket tests、service callback tests、protocol audit。

### 客户端

- 收到 `match_start` 后能获取 allocation/ticket 并把字段传给 Battle transport；
  ticket 缺失、过期或 hash 不匹配时停在 Matching。
- 重试 ticket 请求得到同一 ticket 或明确 replacement，不重复显示两场对局。
- ticket signature/expiry 校验失败时不连接战斗服，不把签名内容写入普通日志。

## 明确不在范围内

C++ tick/输入/快照/Replay 生成、battle result 验签、奖励/排名结算和
玩家资产变更由后续切片及 battle-server-agent 负责。

