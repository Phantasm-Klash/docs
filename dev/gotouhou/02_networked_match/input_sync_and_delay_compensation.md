# 输入同步与延迟补偿

## 输入包

客户端按权威生效 tick 发送输入包：

```json
{
  "input_tick": 1204,
  "seq": 88,
  "ack": 140,
  "dir": 6,
  "slow": true,
  "shoot": true,
  "bomb": false,
  "card_slot": -1
}
```

当前 HTTP MVP 仍使用 `tick` 字段；进入 protobuf/KCP 后协议字段统一为 `input_tick` 语义，`BattleInput.tick` 表示该输入的权威生效 tick。`dir` 使用 bitmask 表示上下左右，服务器负责归一化方向。

## 输入缓冲

- 服务端按 tick 接收输入。
- 输入早到则进入缓冲。
- 输入迟到则使用上一 tick 输入或中立输入，具体规则写入 Replay。
- v0.1 在 60Hz 下建议输入延迟 2-4 tick，约 33-67ms，可按 ping 动态调整。
- `seq` 是连接内严格递增包序号，`ack` 用于确认服务端包或快照，二者不替代 `input_tick`。
- 客户端可上传本地发送时间或本地 tick 作为调试遥测，但不参与权威模拟。

当前 C++ Battle Server 切片先采用保守窗口：只接受 `current_tick < input_tick <= current_tick + max_input_ahead_ticks` 的输入，默认 ahead 窗口为 8 tick；迟到输入拒绝为 `input_tick_too_old`，远未来输入拒绝为 `input_tick_too_far_ahead`，同玩家非递增 `seq` 拒绝为 `seq_replay`。tick 推进时若目标 tick 没有新输入，沿用上一 tick 输入；该策略会写入 replay summary，后续可在完整 Replay 流中显式记录 fallback tick。

## 本地预测

- 客户端输入后立即预测自机移动。
- 低速切换和判定点显示立即响应。
- 射击和 Bomb 可先播放本地表现，但权威结果等待服务器确认。

## 快照修正

- 小偏差：平滑拉回服务器位置。
- 中偏差：短时间插值修正。
- 大偏差：回滚到服务器快照并重模拟本地输入。

## 延迟目标

- 30ms：接近本地手感。
- 80ms：低速操作仍稳定。
- 150ms：可玩但需要更明显预测。
- 250ms：提示网络不佳，排位可限制。

## 注意

命中、擦弹和分数不做客户端最终判定，避免高延迟玩家通过本地画面获得不公平优势。

客户端也不能上传位置、伤害、Boss HP、排名、奖励、掉落、手牌、能量、active_cards 或结算结果。C++ Battle Server 对这些内容有唯一权威，Nakama/Go 只验签并入库。
