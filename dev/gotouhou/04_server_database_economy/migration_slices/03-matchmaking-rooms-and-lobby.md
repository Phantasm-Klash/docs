# 03 匹配、建房与大厅 WSS

## 目标和边界

把 Gensoulkyo 当前由 `runtime/core` 内存 map 驱动的排队、等待房间、房间
快照和大厅通知迁移到 Nakama Go Runtime。完成后，客户端只提交模式/牌组/
房间意图，Nakama/Go 负责资格、规则、canonical deck snapshot、ticket、
roster 和状态广播。

本切片覆盖：

- `matchmaking.join`、`matchmaking.ticket`、`matchmaking.cancel`；
- `rooms.create`、`rooms.list`、`rooms.get`、`rooms.rules`、`rooms.join`、
  `rooms.leave`；
- `rooms.message` / `rooms.chat` / `rooms.announcement` 的大厅消息边界；
- `queue`、`room_state`、`match_start` 前的 WSS/业务事件投影；
- Nakama matchmaker ticket、等待房间恢复、match roster 锁定；
- `match.ready` 的就绪状态记录，但不签发 battle ticket。

明确不在本切片：

- C++ Battle Server 的 tick、输入、快照、KCP/UDP 和实时模式动作；
- Battle Server allocation、signed battle ticket、ticket consume；
- 战斗结果验签、结算、Replay、奖励和活动进度；
- 赛季 leaderboard。匹配评分如有需要只能是 matchmaker property。

## 输入、输出与依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | Nakama authenticated `ctx.UserID`、`mode_id`、`active_deck_id`、可选 `mode_params`、版本戳、幂等 `client_request_id` |
| 服务端补全 | `player_id`、profile、canonical deck snapshot、loadout、mode config、规则 hash、ticket/room/match id |
| 输出 | `QueueResponse`、`RoomSnapshot`、`RoomListResponse`、`RoomRulesSnapshot`、WSS `room_state`/`queue`/`matchmaking` 只读通知 |
| `nakama-server-agent` 输入 | `01` 的 `ctx.UserID`/`identity_link`、`02` 的 `DeckRecord`/deck hash、模式资格与 PhK-Protocol version |
| `nakama-server-agent` 输出 | custom RPC、Nakama matchmaker adapter、room/membership storage、roster lock、WSS event projection、恢复/审计 importer |
| `client-agent` 输入 | Nakama HTTPS/WSS endpoint、`player_id` projection、active deck id、mode intent |
| `client-agent` 输出 | Lobby/Room/Matching 状态机、canonical room code 处理、断线恢复、服务端 roster/rules 渲染 |
| 前置依赖 | `01-auth-and-bootstrap`、`02-inventory-decks-and-chests`、模式资格/ruleset、业务 envelope guard |
| 下游依赖 | `04-battle-allocation-and-ticket` 使用冻结 `match_rosters`；`05` 使用 `match_id` 和 roster |

客户端不得提交或信任以下字段：`match_id`、`ticket_id`、最终玩家人数、
`server_seed`、奖励、分数、伤害、Boss HP、最终结果、客户端计算的
`deck_snapshot_hash`、`loadout.server_authoritative`。这些字段由服务端生成
或仅在响应中投影。

## 当前 Gensoulkyo 的岗位

当前实现集中在：

- `Gensoulkyo/runtime/core/service.go`
  - `JoinQueue`：校验 mode/version/deck/loadout/资格，按
    `mode_id[:rating_code]:stage_id` 排队，达到 `MinPlayers` 后创建 match；
  - `CreateRoom`：生成 canonical room code，创建 host ticket 和 waiting room；
  - `JoinRoom`：校验 room mode/stage/deck/资格，追加成员，达到人数后锁定
    `match_id`；
  - `QueueTicket` / `CancelTicket`：ticket 查询和未匹配取消；
  - `ListRooms` / `Room` / `RoomRules`：等待房间和规则快照；
  - `LobbyMessage`：chat/announcement、消息幂等和审计；
  - `ReadyMatch`：ready 状态与 match start 的旧 core 投影。
- `Gensoulkyo/runtime/nakamaapi/handler.go`
  - 已把上述 RPC 和 WSS-style message dispatch 到 core；
  - 当前 session 映射和 envelope guard 是迁移期 adapter，不是持久化能力。
- `Gensoulkyo/runtime/lobbyws/server.go`
  - 当前用进程内 `rooms`/`matches` client map 广播 room state；
  - room 满员后可启动本地 Battle Server、auto-ready 并广播 match start；
  - 该进程内广播和 spawn 不得被当作 Nakama 重启恢复或 03 的持久化权威。
- `Gensoulkyo/runtime/core/types.go`
  - `CreateRoomRequest` / `JoinRoomRequest` 当前仍允许
    `DeckSnapshot`、`ClientVersion`；
  - `QueueResponse`、`RoomSnapshot`、`RoomRulesSnapshot` 是迁移输出的现有
    shape，应由 Nakama adapter 保持字段兼容。

### 现状到目标的关键差异

1. 当前相同用户重试 `CreateRoom`/`JoinRoom` 会返回既有 waiting room，
   但幂等是内存扫描；目标必须用 `client_request_id` + storage conditional
   write 固化。
2. 当前 `CreateRoom` 忽略客户端传入的旧 `room_code`，由
   `nextRoomCodeLocked` 生成 `R<shortHash>`；目标不得承诺客户端可指定
   canonical code。
3. 当前 `resolveDeckForMatchLocked` 优先读取保存的 active deck，只有兼容
   路径才接受 `DeckSnapshot`；目标主路径只接收 `active_deck_id`，旧
   `deck_snapshot` 只能 shadow/回退校验，不能覆盖保存牌组。
4. 当前 `validateLoadout` 只允许服务端定义的 stage/character/rating；
   `mode_params` 中的 forbidden authority fields 必须继续拒绝。
5. 当前 `RoomRules` 返回业务/战斗传输、操作合同和禁止字段；目标 WSS
   只承载大厅状态，不能承载高频战斗帧。

## 目标 Nakama 面

### 传输和运行时职责

| 面 | Nakama/Go 实现 | 约束 |
| --- | --- | --- |
| HTTPS custom RPC | Go Runtime 注册下表 RPC，owner 从 `ctx.UserID` 取得 | 认证 RPC 之外均要求业务 envelope；不能接受客户端 owner |
| Nakama matchmaker | `matchmaking.join` 内部调用 Nakama matchmaker add；`matchmaking.cancel` 调用 remove | ticket 的业务状态仍写 `matchmaking_tickets`，不能只依赖进程内 matcher |
| waiting room | Go Runtime room coordinator 或 authoritative Nakama match state | storage 做恢复/审计，不做高频广播 |
| WSS/socket | Nakama socket RPC/业务 event 推送 `queue`、`room_state`、`matchmaking` | 断线后以 RPC lookup 重建，不重放客户端本地事件 |
| `04` handoff | 满员后一次性写 `match_rosters`，发布 roster-locked event | 不在 03 中签发 battle ticket |

Nakama API 的具体 SDK 调用由 `nakama-server-agent` 按 pinned Nakama SDK
实现，但语义必须等价于 `matchmaker add/remove`、authoritative room
join/leave、storage conditional write 和 socket notification。不得使用
Nakama leaderboard 代替队列或房间。

### Custom RPC 输入/输出

主路径使用 `POST /v2/rpc/<rpc_id>?unwrap=true`，body 是 double-encoded
JSON string。旧 HTTP `/v1/*` 仅作回退；Nakama context 决定 user，不接受
`user_id`/`player_id` 作为 owner。

| RPC id | 输入类型/字段 | 输出类型/副作用 |
| --- | --- | --- |
| `matchmaking.join` | `MatchmakingJoinRequest{mode_id, active_deck_id, mode_params?, client_request_id, client_version?}` | `QueueResponse`；写 ticket，调用 matchmaker add |
| `matchmaking.ticket` | `TicketLookupRequest{ticket_id}` | `QueueResponse`；只读本人 ticket，越权返回 `not_found` |
| `matchmaking.cancel` | `TicketCancelRequest{ticket_id, client_request_id?}` | `QueueResponse{queue_status:"cancelled"}`；只允许未匹配 ticket |
| `rooms.create` | `CreateRoomIntent{mode_id, active_deck_id, mode_params?, client_request_id, client_version?, room_code?}` | `QueueResponse` 含服务端生成 `room_code`；旧 `room_code` 只审计，不作 key |
| `rooms.list` / `rooms` | `RoomListRequest{mode_id?}` | `RoomListResponse`；只返回 `waiting` 的 participant summary |
| `rooms.get` | `RoomLookupRequest{room_code}` | `RoomSnapshot`；只返回允许展示字段 |
| `rooms.rules` | `RoomLookupRequest{room_code}` | `RoomRulesSnapshot`；返回 version、mode、tick/input delay、禁止字段 |
| `rooms.join` | `JoinRoomIntent{room_code, mode_id?, active_deck_id, mode_params?, client_request_id, client_version?}` | `QueueResponse`；重复加入返回原 ticket，满员时锁 roster |
| `rooms.leave` | `LeaveRoomRequest{room_code, client_request_id?}` | `QueueResponse{queue_status:"cancelled"}`；房主/成员按状态机处理 |
| `match.ready` | `ReadyIntent{match_id}` | `ReadyResponse`；只记录 readiness，不创建 allocation/ticket |
| `rooms.message` / `rooms.chat` | `RoomMessageRequest{room_code, message_id, kind, text, metadata?}` | `LobbyMessage`；同 user+message id 重试返回 `duplicate:true` |
| `rooms.announcement` | 同上，`kind:"announcement"` 且仅 host 可写 | `LobbyMessage`；服务端过滤 authority 字段 |

`mode_params` 只允许 `stage_id`、`character_id`、certification 模式允许的
`rating_code` 以及该模式已冻结的公开参数。`deck_snapshot` 可以在迁移期
兼容输入中出现，但服务端必须优先按 `active_deck_id` 读取 `02` 的 canonical
deck；hash 不一致时返回 `deck_invalid`/`revalidation_required`。

### 响应字段与状态机

`QueueResponse` 的 Nakama JSON 至少包含：

```json
{
  "ok": true,
  "queue_status": "queued",
  "ticket_id": "ticket_opaque",
  "match_id": "",
  "mode_id": "pvp_duel",
  "loadout": {
    "stage_id": "starlit_lanes",
    "character_id": "balanced",
    "rating_code": "",
    "ruleset_version": "ruleset-local-s0",
    "server_authoritative": true
  },
  "room_code": "RABC12",
  "room_status": "waiting",
  "required_players": 2,
  "current_players": 1
}
```

`RoomSnapshot` 至少包含 `room_code`、`room_status`、`mode_id`、
`host_user_id`、`required_players`、`max_players`、`current_players`、
`match_id?`、`stage_id`、`mode_ruleset_version`、`ruleset_version`、
`mode_config_hash`、`mode_params`、`participants`、`messages`、
`created_at`、`server_time`、`server_authoritative`。每个 participant
只含 `user_id`、展示名、服务端生成的 `ticket_id`、`deck_snapshot_hash`、
`loadout` 和 joined/last-seen 时间。

状态转移固定为：

```text
queue ticket: queued -> found | cancelled | expired
room: waiting -> found | cancelled | expired
roster: absent -> locked (exactly once)
```

`found` 后禁止再加入或离开；`match_id`、roster、规则 hash 和每个 deck
snapshot hash 在 `locked` 后不可变。房主离开会取消仍在 waiting 的 room；
普通成员离开只取消自己的 ticket。相同 `client_request_id` 重试必须返回
原结果；相同 key 但请求 hash 不同返回 `idempotency_conflict`。

### WSS / Nakama socket 事件

事件 payload 不携带 session token、原始设备 id、钱包、奖励、战斗结果或
客户端可伪造的 authority 字段。至少定义：

| 事件 | lookup key | payload | 客户端动作 |
| --- | --- | --- | --- |
| `queue` / `matchmaking` | `ticket_id` | `queue_status`、mode、人数、room/match id、loadout、server time | 更新等待状态；断线后调用 `matchmaking.ticket` |
| `room_state` | `room_code` | canonical room snapshot、participants、messages、ruleset | 更新 Room 页面；不从本地 roster 合并 |
| `matchmaking` `found` | `ticket_id`/`match_id` | locked roster 摘要、ruleset/mode hash | 转入准备状态，等待 `04` allocation |
| `business.event` | `kind` + `ticket_id`/`room_code`/`match_id` | 与 RPC lookup 相同的只读投影 | 仅作通知；可丢失，不能作为唯一状态源 |

WSS envelope 保留 `type`、`seq`、`payload`，增加
`server_time`、`ruleset_version`、`request_id?`。服务端接收的写事件继续
检查 `protocol_version`、`seq`、`timestamp`、`nonce`、`op` 和重放窗口。
WSS 不是 `input_packet`、snapshot、card event 或高频 tick 通道。

### Storage / matchmaker / leaderboard

| Nakama 面 | collection/key 或 id | 内容与写入者 |
| --- | --- | --- |
| storage | `lobby_rooms / room_code` | host、mode、status、stage、mode params、ruleset/mode hash、required/max players、created/expiry、version；room Runtime 写 |
| storage | `lobby_room_members / room_code:user_id` | business ticket、deck id/hash、canonical loadout、joined/left/status、request hash；room Runtime 写 |
| storage | `matchmaking_tickets / ticket_id` | user、mode、queue key、Nakama matcher ticket、status、room/match id、request hash、expiry、migration batch；queue RPC 写 |
| storage | `match_rosters / match_id` | locked roster、user/player id、deck snapshot/hash、loadout、protocol/business/battle/ruleset version、mode config hash、locked_at；03 一次性写，04/05 只读 |
| storage | `lobby_idempotency / user_id:client_request_id` | operation、request hash、result reference、created_at；RPC 写 |
| storage | `lobby_audit / event_id` | actor、operation、room/ticket/match、before/after hash、reject reason、created_at；所有状态变更写 |
| matchmaker | query/properties `mode_id`, `mode_ruleset_version`, `mode_config_hash`, `stage_id`, `rating_code?`, `region?` | 只用于候选匹配；不可作为资产或排名权威 |
| leaderboard | **无 id、无写入** | 本切片不调用 `LeaderboardRecordWrite`；匹配分数另开规格 |

Nakama storage 的 owner 必须是 `ctx.UserID` 或服务端固定 owner；客户端不能
指定 collection owner。全局唯一的 `room_code`、`ticket_id`、`client_request_id`
不能只靠 owner-scoped storage 保证；部署 PostgreSQL 时必须增加唯一索引或
通过 Go repository 做 conditional insert。

## 客户端接入点

### LayaAir 网络与状态

- `SpellKard/laya/src/core/net/lobby_client.ts`
  - 保留 `createRoom`、`joinRoom`、`refreshRoom`、`leaveRoom`、
    `joinMatchmaking`、`fetchMatchmakingTicket`、`cancelMatchmaking`、
    `readyMatch` 的公开意图；
  - Nakama transport 使用上述 RPC id；旧 `HttpLobbyTransport` 保留
    `/v1/rooms/*`、`/v1/matchmaking/*` fallback；
  - `createRoom` 成功后必须以响应 `room_code` 覆盖本地输入；不能用旧输入
    拼 `rooms.get`；
  - 请求附带 `active_deck_id`、`mode_params`、版本戳和稳定
    `client_request_id`，不再发送客户端最终 stats/人数/seed；
  - `roomFromPayload` / `matchmakingFromPayload` 只接受服务端 snapshot，
    `match_start` 前不切 Battle。
- `SpellKard/laya/src/core/game/lobby_flow.ts`
  - Lobby/Room/Matching 状态只由 RPC 响应或服务端事件转移；
  - WSS 断线先以 `rooms.get`/`matchmaking.ticket` 恢复，再决定是否重连；
  - `version_mismatch`、`deck_invalid`、`room_unavailable` 停留在可恢复页面，
    不能自动创建第二个 ticket。
- `SpellKard/laya/src/core/net/lobby_protocol.ts`
  - 为 queue/room/matchmaking 事件校验 `seq`、`server_time`、ruleset、
    `room_code`/`ticket_id`/`match_id` 一致性；
  - 保留现有 `RoomState`/`MatchStart` 类型映射，禁止把 WSS 事件当作战斗帧。
- `SpellKard/laya/src/platform/laya/scenes/lobby_scene.ts`
  - 从 preset room code 过渡到 `rooms.list` + 文本输入/服务端 canonical code；
  - 创建、加入、排队按钮以服务端状态和 ticket 幂等为准。
- `SpellKard/laya/src/platform/laya/scenes/room_scene.ts`
  - 显示 mode/ruleset、canonical room code、人数、participant loadout；
  - 不显示或编辑 deck hash、server seed、奖励和战斗结果。

### 传输选择

| 操作 | 主路径 | 回退 |
| --- | --- | --- |
| 创建/加入/查询 room、queue ticket | Nakama HTTPS RPC | Gensoulkyo `/v1/*` HTTP |
| queue/room 状态通知 | Nakama socket/WSS `business.event`/room event | ticket/room 轮询 |
| chat/announcement | Nakama socket RPC/event | 旧 lobby WSS message |
| 战斗输入/快照 | 不属于本切片 | 04/PhK-BattleServer 规定的战斗通道 |

## 数据迁移

### 导入范围

从旧 Gensoulkyo 导出：

```text
legacy_user_id -> nakama_user_id
active ticket: ticket_id, mode_id, queue status, room_code, created_at
waiting room: canonical room_code, host, mode, stage, mode_params, members
member: active_deck_id, deck_snapshot_hash, server loadout, joined_at
source_state_hash, export_at
```

不导入过期 ticket、已匹配但没有 locked roster 的半成品 match、不导入 session
token、原始设备 id、客户端提交的最终战斗字段。

### 迁移顺序

1. 用 `01` 的 `identity_link` 映射 legacy user；冲突用户标为
   `rejected`，不创建第二个 owner。
2. 用 `02` 读取 canonical deck，重新计算 `deck_snapshot_hash`、
   `mode_config_hash` 和 loadout；旧 hash 不一致时标为
   `revalidation_required`，不能自动入队。
3. 先导入 `lobby_rooms`、`lobby_room_members`、`matchmaking_tickets` 的
   `shadow` 记录，写 `migration_batch_id`、source/target hash 和状态。
4. 运行 shadow compare：旧 core 的 waiting room/ticket 与 Nakama 查询结果
   在 mode、stage、成员顺序、deck hash、人数和状态上完全一致。
5. 切换创建权前冻结 legacy queue 写入，等待旧请求结束；每个 active ticket
   只允许一个 authority 发 `match_start`。
6. 切换后新建房/入队直接写 Nakama；旧 ticket 只读并按原 room code lookup，
   不把 `requested_room_code` 当作 `lobby_rooms` key。
7. 满员时以 conditional write 创建 `match_rosters/match_id`；重复回调返回
   相同 locked roster，不创建第二个 match。

迁移状态至少为 `pending`、`shadow_match`、`active`、
`revalidation_required`、`orphan`、`rejected`。迁移脚本必须按
`legacy_user_id`/旧 ticket 重跑而不覆盖已 `active` 的 canonical state。

## 回滚策略

- 开关 `lobby_authority=legacy|shadow|nakama`；`shadow` 只比较 hash，不创建
  Nakama ticket，不广播第二份状态。
- 切回前停止 Nakama `matchmaking.join` 和 `rooms.create/join` 写入口，保留
  ticket/room lookup；取消或等待未匹配 Nakama ticket 后再开放 legacy queue。
- 已写入 `match_rosters` 的 locked match 不跨 authority 继续创建第二个 roster；
 由 `04` 按 match id 决定取消或继续 allocation。
- WSS 重连一律通过 `rooms.get`/`matchmaking.ticket` 查询 canonical snapshot；
 不能依据本地旧 event 重放，也不能用新 request id 自动重入。
- 回滚不删除 `lobby_*`、`match_rosters`、idempotency 或 audit 记录。恢复
  Nakama 时先按 ticket/request hash 对账，已 `found`/`locked` 的记录只读。
- 出现 room/ticket 全局唯一冲突、deck hash 不一致、双重 match start 或
  storage conditional write 失败时，关闭创建/入队写入，只保留查询并报警。

## 验收测试

### 服务端最小命令

先在 Gensoulkyo 工作树执行：

```bash
cd /root/gotouhou/Gensoulkyo
go test ./runtime/core ./runtime/nakamaapi ./runtime/lobbyws ./runtime/security
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

若 `go test -tags nakama` 或 plugin build 因 pinned Nakama SDK/网络不可用
失败，必须报告首个依赖错误；无 tag 测试不能替代 plugin 验收。

### 服务端断言清单

1. 同一 user 的重复 `client_request_id` 返回同一 ticket/room，且不会创建
   第二个 storage record；同 key 不同 request hash 返回
   `idempotency_conflict`。
2. 非法 mode、未解锁 rating、非法 stage/character、未保存 deck、版本不兼容、
   forbidden authority field 均拒绝，且没有 matcher/member/room side effect。
3. `rooms.create` 忽略旧 `room_code` 的权威意义并返回唯一 canonical code；
   `rooms.list` 只列 `waiting` room。
4. 重复 `rooms.join` 返回原 ticket；达到 `min_players` 只产生一个
   `match_id` 和一个 `match_rosters`；第三人被拒绝。
5. 房主离开、普通成员离开、重复取消、已匹配后取消符合状态机；已 found
   的 room 不允许再入/离。
6. `rooms.rules` 的 `ruleset_version`、`mode_ruleset_version`、
   `mode_config_hash`、tick/input delay 与 locked roster 输入一致。
7. storage/instance 重启后 waiting room、ticket、members、audit 可恢复；
   重复恢复不会再次发 `match_start`。
8. WSS seq/nonce 重放、越权读取他人 ticket、伪造 participant/loadout、
   token/奖励/战斗字段泄漏均失败。
9. 本切片不调用 leaderboard write；匹配 score 不出现在资产/排名快照。

### 客户端断言清单

1. `LobbyClient` 能用 Nakama RPC 和旧 HTTP fallback 完成
   create/list/get/rules/join/leave、join/ticket/cancel；两个传输解码到同一
   `RoomView`/`MatchmakingTicketView`。
2. 建房成功后使用响应 `room_code`；服务端生成 code 与旧输入不一致时仍能
   `rooms.get`，不会访问一个客户端自造的 code。
3. 重试沿用同一 `client_request_id`，断线恢复先 lookup，不创建第二个 ticket。
4. 本地篡改人数、玩家 ready、deck hash、mode status、奖励等字段不影响下一次
   请求和页面显示；客户端只渲染 server projection。
5. 收到旧 ruleset、缺少 match id、`room_unavailable`、`deck_invalid` 时停留
   在可恢复 Lobby/Room/Matching 状态；未收到 `match_start` 不进入 Battle。
6. WSS `room_state`/queue 事件可丢失后由 HTTPS lookup 修复；事件 seq/room/
   ticket/match 关联错误被拒绝。

最小客户端命令：

```bash
cd /root/gotouhou/SpellKard/laya
npm run typecheck
npm test
```

## 交付物与完成判定

`nakama-server-agent` 必须交付：

- RPC/WSS 注册和 envelope/owner/authz 校验；
- matchmaker add/remove、room coordinator、storage collections/index、
  idempotency、roster lock、audit 和 migration importer；
- instance restart/recovery 测试及 `04` 可消费的 `match_rosters` contract。

`client-agent` 必须交付：

- Nakama/HTTP 双传输和上述 request/response decoder；
- canonical room code、active deck/version/request id、断线恢复和 WSS event
  投影；
- Lobby/Room/Matching 页面与测试。

只有在 `match_rosters` 可重启恢复、重复请求不会重复入队/发 match id、客户端
不接受伪造 authority 字段、并通过协议审计后，本切片才算完成。Battle Server
的 allocation/ticket 由 `04` 单独验收。
