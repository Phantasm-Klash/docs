# 对局状态快照

## 快照用途

快照用于客户端显示权威状态、纠正预测偏差、断线重连和 Replay 校验。

## 快照频率

- v0.1 服务端 60Hz 模拟，每 2-4 tick 下发一次快照，即约 15-30 snapshot/s。
- 高延迟或观战模式可降低频率。
- 关键事件 tick 必须立即发送事件包。

## 快照内容

```json
{
  "match_id": "uuid",
  "tick": 1204,
  "state_hash": "hex",
  "players": [],
  "bullets_delta": [],
  "score": [],
  "active_cards": [],
  "mode_state": {},
  "events": []
}
```

## 全量与增量

- 刚进入房间或重连时发送全量快照。
- 正常对局发送增量快照。
- 客户端若检测丢包或 hash 不一致，请求全量快照。

## 子弹同步

- 高频弹体不逐颗频繁同步全部属性。
- 服务端同步生成事件、关键变速事件和校验摘要。
- 客户端用相同确定性模拟重建弹幕表现。
- 协议层使用定点整数 delta，例如 `x_milli`、`y_milli`、`vx_milli`、`vy_milli` 和 `radius_milli`。
- C++ 迁移后，state_hash 覆盖 tick、玩家状态、子弹摘要、active card、RNG 状态和模式摘要；Go MVP 的 JSON hash 只作为迁移期调试信号。
- 当前 C++ Battle Server 切片已经输出镜像 `BattleSnapshot` 的 dependency-light 结构：`snapshot_tick`、`snapshot_kind`、`state_hash`、`players`、`bullets_delta`、`mode_state.tick_rate_hz` 和 `event_cursor`。现阶段 `bullets_delta` 是简化全量 upsert；后续接入真实 protobuf/KCP 后再拆分增量 delta、关键事件和重连全量快照。

## 结算快照

结算快照必须包含最终分数、胜负、奖励摘要和 replay_id。客户端不能自行推导奖励。

## 模式状态

`mode_state` 用于携带模式特有摘要：

- 考证：rating_code、rank_score_preview、challenge_progress。
- 大逃杀：round_index、choice_deadline_tick、public_pool_hash、zero_round_order。
- 世界 Boss：boss_hp_preview、daily_attempts_left、transfer_requests。
- 副本 Boss：boss_phase、party_status、clear_conditions。

模式状态只用于展示，最终结算仍以服务端结果为准。
