# 多人延迟测试

## 测试场景

- 30ms 延迟。
- 80ms 延迟。
- 150ms 延迟。
- 250ms 延迟。
- 1%-5% 丢包。
- 抖动。
- 短断线。
- 重连。

## 测试内容

- 高速移动。
- 低速精密躲避。
- Bomb。
- 决死。
- 擦弹。
- 卡牌施放。
- 快照修正。
- 大逃杀 30 秒回合倒计时。
- 世界 Boss 卡牌让渡。
- Boss 模式多人站位和朝向。
- 考证模式结算。

## 指标

- input_delay_ticks。
- average_position_error。
- correction_count。
- hard_snap_count。
- late_input_count。
- perceived_hit_mismatch。
- reconnect_success_rate。

## 验收

- 80ms 下低速移动手感稳定。
- 150ms 下仍可完成休闲对局。
- 命中结算以服务器为准，客户端表现不产生明显误导。
- 重连后 Replay 和结算一致。
- 大逃杀回合选择在高延迟下不漂移。
- Boss 卡牌让渡请求在高延迟下不重复。
- 考证模式 rank 分不受客户端延迟影响。

## 工具

本地可用网络模拟工具制造延迟、丢包和抖动。测试结果写入报告并附对应 replay_id。
