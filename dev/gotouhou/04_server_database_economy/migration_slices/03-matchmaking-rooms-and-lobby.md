# 03 匹配、房间与大厅 WSS

## 目标和边界

把当前 core 内存队列/房间和 Nakama adapter 的 lobby RPC/WSS 迁移为
Nakama matchmaker、authoritative match 或 Go Runtime 编排。切片输出等待房间、
队列 ticket、房间状态、规则快照和 match id；不负责 C++ 战斗 tick、battle
ticket 签名、结算或奖励。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | authenticated `user_id`/`player_id`、`mode_id`、`mode_params`、`room_code`、active deck id、业务 envelope |
| 输出 | queue ticket、room snapshot、rules snapshot、match id、服务端锁定的 deck snapshot hash |
| 前置依赖 | `01` 身份/bootstrap、`02` canonical deck、模式资格/ruleset、业务 WSS envelope |
| 下游切片 | `04` 使用 match roster 分配战斗服；`05` 使用 match id 接收结算 |
| 实现归属 | `nakama-server-agent`：matchmaker/room runtime、RPC/WSS、持久化审计；`client-agent`：Lobby/Room/Matching 状态接入 |

## 当前 Gensoulkyo 的岗位

- `matchmaking.join`、`matchmaking.ticket`、`matchmaking.cancel` 操作 core
  内存 queue ticket，服务端决定 match 创建。
- `rooms.create/list/get/rules/join/leave` 管理等待房间，加入时校验 mode、
  stage、deck snapshot 和资格；达到人数后产生 allocation。
- WSS 推送 `room_state`、`match_start`、`match_result`，客户端仅消费服务端
  状态。业务 envelope guard 已要求 seq/timestamp/nonce/replay audit。
- 房间快照只显示 user/player、ticket、loadout 和 deck hash，不显示客户端可
  伪造的伤害、分数、奖励、Boss HP 等权威结算字段。

## 目标 Nakama 契约

### RPC/WSS

保留下列 custom RPC id，降低客户端切换成本：

| RPC | 输入 | 输出 | 说明 |
| --- | --- | --- | --- |
| `matchmaking.join` | `mode_id`、`mode_params`、`active_deck_id`、`client_request_id` | `ticket_id`、queue status、server time | Go Runtime 校验 deck/资格后调用 Nakama matchmaker |
| `matchmaking.ticket` | `ticket_id` | ticket status、`match_id`、players-ready 状态 | 只读当前用户 ticket |
| `matchmaking.cancel` | `ticket_id`、幂等键 | cancelled status | 仅未匹配 ticket 可取消 |
| `rooms.create` | `room_code`、`mode_id`、`active_deck_id` | room snapshot、host ticket | room code 由服务端规范化/冲突检查 |
| `rooms.list` | mode/filter | waiting room summaries | 不泄露未公开字段 |
| `rooms.get` | `room_code` | room snapshot | 仅返回允许展示的 participant view |
| `rooms.rules` | `room_code` | protocol/ruleset/mode hash、tick、input delay、ticket TTL、禁止字段 | 版本快照 |
| `rooms.join` | `room_code`、`active_deck_id` | room snapshot、ticket/match if ready | 服务端重算 deck snapshot |
| `rooms.leave` | `room_code`、幂等键 | room status | 房主离开取消房间，其他人只撤销自己 |

Nakama standard matchmaker 是队列面；自定义 authoritative match 或 Go Runtime
room state 是房间面。不能把 PostgreSQL/Nakama storage 当作高频房间广播通道。
WSS message types 保持 `room_state`、`match_start`、`match_result`，消息 envelope
保留 `type`、`seq`、`payload`，并新增 `server_time`/`ruleset_version` 校验。

### Storage 和临时状态

| collection | key | 内容 | 生命周期 |
| --- | --- | --- | --- |
| `lobby_rooms` | `room_code` | host、mode、status、ruleset/mode hash、required players、created/expired at | 等待/审计期间 |
| `lobby_room_members` | `room_code:user_id` | ticket、deck snapshot hash、loadout、joined/left/status | 对局启动后只读审计 |
| `matchmaking_tickets` | `ticket_id` | user、mode、queue status、match id、request hash、expiry | ticket TTL + audit |
| `match_rosters` | `match_id` | player ids、user ids、deck hashes、locked ruleset | 结算完成后归档 |
| `lobby_audit` | `event_id` | operation、actor、room/match、before/after hash、reject reason | 长期审计 |

leaderboard 本切片不写入；匹配评分可作为 Nakama matchmaker properties，
但不可直接当作赛季 leaderboard 分数。storage 写入必须带 conditional version
和幂等键，房间状态广播以 authoritative match 内存状态为准。

## 客户端接入点

- `lobby_client.ts` 现有 `createRoom`、`joinRoom`、`leaveRoom`、
  `refreshRoom`、`joinMatchmaking`、`fetchMatchmakingTicket`、
  `cancelMatchmaking` 方法保持名称和返回投影。
- `lobby_protocol.ts` 继续注册 bootstrap/room WSS route；补齐 matchmaking
  progress、room rules、ticket expiry 和 `match_start` 的字段校验。
- `lobby_flow.ts` 的 Lobby/Room/Matching 状态只根据服务端事件转移。轮询
  ticket 是迁移期 fallback，WSS 推送可用后优先推送，轮询只作断线恢复。
- 建房/入房前客户端传 `active_deck_id` 和 mode intent；不传 cards 的最终
  stats、玩家人数结算、战斗 seed 或奖励。

## 数据迁移

1. 不迁移已过期 queue ticket；只导出 active ticket、waiting room、成员、
   mode/ruleset 和 source state hash。
2. 用 `identity_link`、canonical deck 和当前 ruleset 重建 room/member；
   deck snapshot hash 不一致的成员置为 `revalidation_required`，不能直接
   进入 match。
3. 先把 Nakama matchmaker/room 设为 shadow：旧 core 仍做决定，Nakama 只
   计算候选 roster 并写审计；候选与旧 roster 一致后切换创建权。
4. 切换时每个 active ticket 写入 `migration_batch_id` 和旧 ticket id，
   保留旧 room code；禁止双系统同时向同一玩家发送 `match_start`。

## 回滚策略

- `lobby_authority` 支持 `legacy`、`shadow`、`nakama`。切换窗口只允许一个
  authority 发放 queue ticket 和 match id。
- 切回时先停止 Nakama 入队和广播，等待或取消 Nakama ticket，再恢复旧
  queue；已经产生 match id 的队伍不跨 authority 继续，转由 `04` 的分配
 规则判定取消或完成。
- WSS 重连通过 match id/room code 重新读取 snapshot，不能依据旧本地事件
  重放状态。所有取消/离房操作保留 audit，防止回滚后重复入队。

## 验收测试

### 服务端

- 同一 user 不能同时拥有两个有效 queue ticket；相同 client request id
  重试返回同一 ticket。
- 非法 mode、无资格、active deck 不存在/未保存、规则版本不兼容均拒绝，
  且不产生房间成员或 matcher side effect。
- 房间 code 冲突、房主离开、普通成员离开、达到人数后锁定 roster 的状态
  转移符合契约；`rooms.rules` 与 allocation 输入 hash 一致。
- WSS seq/nonce 重放、越权读取其他用户 ticket、伪造 participant 权威字段
  均拒绝；广播不包含隐私 token、战斗结果或奖励。
- Nakama instance/reconnect 后能从 storage 恢复 waiting room 和 ticket；
  match start 只产生一次。
- 运行 Go Runtime tests、Nakama `docker-compose` 与 PostgreSQL 恢复测试，
  再运行 protocol audit。

### 客户端

- Lobby/Room/Matching 页面覆盖 create/list/get/rules/join/leave、排队、
  轮询和 WSS 推送；断线后不重复创建 ticket。
- 收到 `match_start` 前不进入 Battle；收到旧 ruleset 或缺少 match id 时
  显示可恢复错误并回 Lobby。
- 房间快照只渲染服务端字段；客户端修改本地玩家数、deck stats 或 status
  不影响后续请求。
- 使用 LayaAir live check 验证 HTTPS fallback 与 WSS route 的结果投影一致。

## 明确不在范围内

C++ 战斗连接、battle allocation/ticket、匹配评分 leaderboard、战斗结算、
Replay 和活动奖励不由本切片实现。
