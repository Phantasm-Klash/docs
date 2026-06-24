# 练习与调试模式

## 练习模式

练习模式用于学习弹幕、背版、测试卡组和验证手感。

功能：

- 选择弹幕模式和阶段。
- 设置起始 tick。
- 锁定或随机 seed。
- 调整自机、卡牌、火力和 Bomb 数。
- 支持无限重试和快速重开。

## 调试显示

可选显示：

- 自机判定点。
- 擦弹圈。
- 子弹判定圆。
- 弹幕生成器位置。
- 当前 tick。
- FPS、逻辑 tick 耗时、同屏弹数。
- 最近输入和服务器快照。

## Replay 分析

- 标记命中点、Bomb 点、最大连段中断点。
- 显示每段得分来源。
- 显示危险弹来源和模式 ID。

## 联机调试

开发版允许打开网络覆盖层：

- ping。
- jitter。
- packet_loss。
- input_delay_ticks。
- rollback_or_correction_count。
- snapshot_age_ticks。
