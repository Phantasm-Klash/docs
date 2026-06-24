# Replay 校验

## 目标

同一 Replay 在同一规则版本下，多次播放必须产生相同结果。

## 校验流程

1. 读取 replay。
2. 加载 ruleset_version。
3. 使用 match_seed 初始化 RNG。
4. 按 tick 重放输入流和卡牌事件。
5. 生成 final_result_hash。
6. 与保存 hash 对比。

## 校验范围

- 玩家位置。
- 弹幕摘要。
- 擦弹数。
- 命中数。
- 分数。
- 卡牌状态。
- 模式状态，如评级、回合、大逃杀公共卡池、Boss 血量和星级。
- 胜负。

## 不一致处理

- 标记 replay_invalid。
- 输出首个不一致 tick。
- 保存 state_hash 差异。
- 判断是规则版本不兼容还是模拟非确定。

## 自动化

CI 中保留一组 golden replay。任何对逻辑规则的修改都必须确认 replay 变化是否符合预期。

## 线上

玩家争议对局以服务端 Replay 校验为准。客户端本地回放只用于展示。
