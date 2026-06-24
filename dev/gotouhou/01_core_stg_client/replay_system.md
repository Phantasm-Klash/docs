# Replay 系统

## 定位

Replay 不是视频文件，而是确定性重演所需的数据包。它用于玩家复盘、争议复核、反作弊分析、性能对比和教程制作。

## 本地 Replay 内容

- game_version。
- ruleset_version。
- match_seed。
- player_config。
- deck_snapshot。
- input_stream。
- card_event_stream。
- final_result_hash。

Replay 不保存显示文本、主题素材或 Workshop Mod 内容，只保存稳定 code、i18n key、seed 和输入事件。

## 输入流

每个 tick 记录：

- direction_bits。
- slow_pressed。
- shoot_pressed。
- bomb_pressed。
- card_slot。
- client_prediction_frame 可选，仅用于调试。

## 播放功能

- 播放、暂停、继续。
- 2x、4x、8x 快进。
- 0.5x 慢放。
- 跳转到关键 tick。
- 显示判定点、擦弹圈、事件日志的调试模式。

## 校验

- 重放结束后计算 result_hash。
- result_hash 必须与保存值一致。
- 不一致时标记为版本不兼容或模拟非确定。

## 线上 Replay

线上 Replay 以服务端权威输入流、seed、卡牌事件和结算为准。客户端本地预测数据不能作为复核依据。

观看 Replay 时，卡牌名称和描述使用观看者当前语言包和主题包渲染；若主题缺失，则回退到基础主题文本。
