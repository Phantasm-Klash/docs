# 05 结算、Replay 与战斗结果回调

## 目标和边界

把 C++ Battle Server 的 signed result callback 接入 Nakama/Go，完成结果验签、
match/roster/ruleset/replay summary 校验、幂等结算、Replay audit 和奖励/进度
事件投递。客户端只能读取自己的 settlement/replay；不能提交分数、伤害、奖励、
排行榜分数或 Boss HP。本切片不定义活动领取 UI，也不实现 Battle Server 的
实时模拟。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | service-origin `SignedBattleResult`、`ReplayInputStreamSummary`、`match_id`、battle server identity |
| 输出 | `BattleResultSubmitResponse`、每用户 settlement、`ReplayRecord`、内部 reward/progress/leaderboard event |
| 前置依赖 | `03` 锁定 roster、`04` allocation/ticket、Battle Server 签名公钥、`02` economy ledger、模式结算规则 |
| 下游切片 | `06` 消费任务/活动/排行榜更新并处理 claim；客户端 Result/Replay 页面读取 |
| 实现归属 | `nakama-server-agent`：callback RPC、验签、storage transaction、幂等/审计；battle-server-agent：签名 result/replay summary；`client-agent`：结果与 Replay 读取 |

## 当前 Gensoulkyo 的岗位

- `battle.result.submit` 只接受 service-origin callback，检查版本、签名形状、
  result hash、replay id、玩家列表、settled time 和禁止客户端字段。
- core 以 `match_id + user_id` 作为 settlement key，重复提交返回 duplicate，
  不重复发奖；生成 `ReplayRecord` 并写 battle/replay audit。
- 结算派生 `RewardJSON`、`TaskProgress`、`EventPoints`、`LeaderboardUpdates`
  和 certification/world boss mode result；客户端收到的 result 是投影，不是
  结算 authority。
- `replay.get` 只允许 match participant 读取自己的 Replay。

## 目标 Nakama 契约

### Service callback

保留 `battle.result.submit` custom RPC，但只允许 battle-server service identity
调用，不能使用玩家 Nakama session：

```json
{
  "signed_result": {
    "result": {
      "protocol_version": 1,
      "business_api_version": "v0.1",
      "battle_api_version": "v0.1",
      "ruleset_version": "ruleset-local-s0",
      "match_id": "match-id",
      "mode_id": "pvp_duel",
      "result_hash": "sha256:...",
      "replay_id": "replay-id",
      "player_ids": ["p-..."],
      "settled_at_ms": 1760000000000
    },
    "signature_alg": "ED25519",
    "key_id": "battle-key-id",
    "signature_hex": "...",
    "server_authoritative": true
  },
  "replay_summary": {
    "replay_id": "replay-id",
    "match_id": "match-id",
    "owner_user_id": "user-id",
    "input_count": 1,
    "event_count": 1,
    "input_stream_hash": "sha256:...",
    "event_stream_hash": "sha256:...",
    "final_state_hash": "sha256:...",
    "final_tick": 1
  }
}
```

成功响应保持 `BattleResultSubmitResponse`：
`accepted`、`duplicate`、`match_id`、`settlement_key`、`server_time`。
签名、key、match、roster、ruleset、mode hash、ticket consumption 和 replay
summary 任一不一致都拒绝；错误码使用 `invalid_request`、
`service_origin_required`、`signature_invalid`、`match_state_invalid`、
`result_conflict`、`already_settled`、`storage_unavailable`。

### 玩家读取

- `business.event.settlement`：认证玩家读取自己已完成的 settlement receipt；
  只返回服务器生成的 result/reward projection。
- `replay.get`：输入 `replay_id`，仅 match participant 可读；
  返回 `ReplayRecord` 和 hash summary。完整输入流可返回 object-storage
  reference，不把大 blob 塞入 Nakama storage 单条记录。

### Storage 和 leaderboard 面

| collection | key | 内容 |
| --- | --- | --- |
| `matches` | `match_id` | mode/ruleset/seed hash、roster hash、status、started/ended/settled |
| `match_players` | `match_id:user_id` | player/deck snapshot、结果、score/stats、reward projection |
| `battle_results` | `match_id:result_hash` | signed result、key id、verified status、received/settled at |
| `settlements` | `match_id:user_id` | settlement key、result、reward/progress projection、duplicate state |
| `replays` | `replay_id` | match/user、ruleset、state/input/event hashes、counts、object reference |
| `settlement_audit` | `match_id:event_id` | verify/reject/settle reason、source service、request hash |
| `reward_ledger` | `settlement_key:grant_id` | 已应用 grant、资产变化、source、idempotency key |

leaderboard 由已验证结算在 Nakama authoritative leaderboard 面写入：

| leaderboard id | score 来源 | 重复/回滚规则 |
| --- | --- | --- |
| `single_score` | 结算中的单局分数 | `settlement_key` 去重，按赛季隔离 |
| `rank_score` | certification/ranked 规则派生的 rating score | 只接受服务端 score，保留旧 score 审计 |
| `world_boss_damage` | 已验签的 Boss damage | 按 boss season/instance metadata 隔离 |

排行榜写入与 settlement transaction 必须有 outbox/重试状态；不能在客户端
直接调用 Nakama leaderboard write。若 leaderboard 暂时不可用，结算和 reward
ledger 仍保持可对账，稍后由可靠 worker 补写。

## 客户端接入点

- `lobby_client.ts` 保留 `fetchReplay(replayId)`；增加
  `fetchSettlement(matchId)` 或通过现有 settlement event 读取结果。
- `lobby_flow.ts` 收到 `match_result` 后只展示服务端投影，返回 Result 页面；
  Replay 页面按需读取 `replay.get`，校验 `replay_id/match_id/user_id` 归属。
- `lobby_protocol.ts` 的 `match_result` 只接受服务端字段；客户端不得把本地
  分数、奖励或 hash 反写回 RPC。
- 结果通知优先 Nakama WSS；HTTPS RPC 用于断线补读。Replay 大对象使用服务端
  授权 URL/受控下载，不把 token 放进 query 或日志。

## 数据迁移

1. 从现有 `matches`、`match_players`、内存 `settlements`/`replays` 和
   battle audit 导出已完成对局、settlement key、replay/hash、reward projection。
2. 只导入能与 `03` roster、`04` ticket/allocation 和 ruleset 对上的结果；
   无法验签或缺 roster 的记录进入 `rejected_results` 审计，不自动发奖。
3. 以 `match_id:user_id` 重建 settlement，以 `replay_id` 重建 Replay；
   已存在的 reward ledger/leaderboard 更新带原 settlement key，导入为
   applied，避免迁移后重复发放。
4. 新旧双读比较 match status、result hash、Replay state hash、reward grant
   和 leaderboard score；所有差异保留源快照，停止该 match 切换。

## 回滚策略

- `settlement_authority` 支持 `legacy`、`shadow`、`nakama`；shadow 只验签、
  计算差异并写审计，不发奖、不写 leaderboard。
- 进入 Nakama 后，旧系统不再接收同一 match 的 result callback。回滚前冻结
  新结算，按 settlement key 对账后只切换未处理 match。
- 已 accepted/settled 的结果、reward ledger、leaderboard score 和 Replay
  不删除、不反向重放；需要纠错时使用补偿/更正 ledger 和管理员审计。
- 签名 key 撤销或 Replay hash 冲突时，保留 settlement 读路径但暂停发奖和
  leaderboard outbox，等待人工复核。

## 验收测试

### 服务端和 Battle Server

- 合法 signed result 首次接受并生成每个玩家 settlement、Replay audit 和
  reward ledger；相同 payload 重试返回 `duplicate`，不重复发奖。
- 修改 result hash、signature、key、match/player list、ruleset、replay
  summary、settlement time 或 forbidden reward field 均拒绝。
- 非 service-origin/玩家 session 调用 callback 被拒绝；服务端提交不可伪造
  的 reward/leaderboard projection，客户端字段不能穿透。
- `replay.get` 做 participant authorization；Replay hash/count/final tick
  与 battle result 对账；object storage 不可用时有可恢复状态。
- leaderboard/reward worker 重试不产生重复 score 或 grant；数据库/Nakama
  重启后 settlement key 仍可查询。
- 用 `docker-compose` 启动 Nakama/PostgreSQL/Battle Server stub，运行
  signed-result、idempotency、replay audit 和 protocol audit。

### 客户端

- 收到 `match_result` 能显示服务端结果并进入 Result；重复通知不重复加奖励。
- 断线后用 `fetchSettlement`/事件补读恢复同一 settlement；Replay 非本人
  或 hash 不匹配时不展示为可信战报。
- Replay 下载失败可重试，不重新提交 battle result，也不泄露 session token。

## 明确不在范围内

实时战斗输入/快照、Battle Server 模拟、卡池抽样、活动 claim UI、Steam
商业掉落和管理员更正工具不在本切片。
