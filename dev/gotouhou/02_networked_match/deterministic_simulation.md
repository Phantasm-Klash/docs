# 确定性模拟

## 目标

同一 match seed、同一输入流、同一规则版本，应产生完全一致的对局结果。

## 固定 tick

- 服务端使用固定 tick 更新。
- v0.1 锁定 60 tick/s，与当前 Gensoulkyo `TickRate = 60` 和客户端 60 FPS 渲染对齐。
- 客户端渲染可 60 FPS 或更高，但不能影响逻辑。
- tick rate 写入 protocol/ruleset 兼容信息；若未来降到 30 tick/s，必须作为新 ruleset 迁移，不能在同一对局内混用。

## 数值表示

- 位置、速度、角度优先使用整数或定点数。
- 若使用浮点，必须限制在同一运行环境中由服务端权威生成。
- Replay 校验以服务端结果为准。
- C++ 战斗服迁移后，位置、速度、半径使用 milli 单位或 Q 格式整数；角度由固定查表、整数角度或服务端生成后的整数速度表示。
- state_hash 使用 canonical binary/state digest，不以 Go/Godot/C++ 各自 JSON 序列化作为长期标准。

## RNG

随机数输入：

- match_seed。
- tick。
- pattern_id。
- spawn_index。
- card_event_id。

禁止使用：

- 系统时间。
- 本地帧率。
- 非确定性容器遍历顺序。
- 客户端随机结果。

## 状态哈希

关键 tick 可生成 state_hash：

- 玩家位置。
- 弹幕数量和摘要。
- 分数。
- 卡牌状态。
- RNG 状态。

state_hash 用于 Replay 校验和线上问题排查。

## 当前实现复盘

- Gensoulkyo Go MVP 已能用服务端 seed、tick 和稳定排序生成弹幕、快照和短 state_hash，但仍使用 `float64` 和 JSON hash，只能作为契约 MVP。
- PhK-Protocol 的 `BattlePlayerSnapshot`、`BattleBulletDelta` 已开始使用 milli 定点字段，C++ 迁移应沿用该方向。
- C++ Battle Server 已开始权威战斗核心切片：固定 `kBattleTickRateHz = 60`、按 `BattleInput.tick` 缓冲输入、验证玩家/seq/输入窗口/方向 bit/card slot、使用 milli 整数推进玩家和简化径向弹幕，并输出镜像 `BattleSnapshot` 的玩家/子弹 delta、`mode_state.tick_rate_hz`、canonical FNV-1a `state_hash` 和 replay summary hash。该切片仍是 v0.1 dependency-light 实现，尚未覆盖命中、擦弹、Bomb、卡牌、Boss、真实 protobuf 序列化和加密传输。
