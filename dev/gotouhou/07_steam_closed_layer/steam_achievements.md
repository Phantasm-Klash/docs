# Steam 成就与统计

## 成就来源

成就由服务端权威事件触发，客户端只负责展示同步结果。

示例：

- 完成首局对战。
- 达成指定擦弹数。
- 使用不同卡组获胜。
- 上传或启用 Workshop 主题。
- 完成赛季活动。
- 通过评级考证。
- 赢得大逃杀。
- 参与击败世界 Boss。
- 完成副本 Boss 星级挑战。

## 统计

可同步：

- total_matches。
- wins。
- graze_total。
- replay_saved。
- chests_opened。

## 同步策略

- 对局结束后服务端计算成就条件。
- 闭源 Steam 层同步 Steam Stats/Achievements。
- 客户端收到同步结果后展示。

## 开源版

开源版保留本地成就接口或空实现，不依赖 Steam。
