# 对局持久化

## 保存目的

- 战绩查询。
- Replay 下载。
- 奖励结算。
- 争议复核。
- 平衡分析。
- 反作弊审计。

## 对局开始

创建 `matches`：

- match_id。
- mode。
- mode_ruleset_version。
- ruleset_version。
- server_seed。
- status。
- started_at。

创建 `match_players`：

- user_id。
- side。
- deck_snapshot_json。
- mode_snapshot_json。
- 初始分数和统计。

## 对局中

关键事件写入 `match_events`：

- cast_card。
- mode_action。
- hit。
- bomb。
- deathbomb。
- phase_change。
- disconnect。
- reconnect。
- state_hash_checkpoint。

高频输入流可保存为压缩 blob 或外部对象存储引用，避免数据库行过大。

C++ Battle Server 迁移期会随结算提交 replay summary：输入流 hash、事件流 hash、最终 state hash、final_tick、input_count 和 event_count。Nakama/Go 入库时应把这些摘要与 signed result、battle_server_build_id 和 mode_config_hash 一起保存，用于排查 replay 缺失、重复结算和跨语言确定性差异。

## 对局结束

- 更新最终 score、graze_count、hit_count、result。
- 写入 reward_json。
- 标记 matches.status 为 completed。
- 生成 replay_id。
- 触发排行榜和任务进度更新。
- 触发基础掉落判定。Steam 商业服的 Steam Inventory 掉落由闭源适配层执行。

## 模式持久化

- 考证模式保存 rating_code、挑战结果、rank 分变化和 top 30% 资格。
- 大逃杀保存公共卡池、第零回合排名、每回合 3 选 1 候选卡和选择。
- 世界 Boss 保存 boss_instance_id、玩家伤害、让渡事件、Boss 扣血和世界通告状态。
- 副本 Boss 保存 boss_instance_id、是否通关、用时、星级和失败原因。

## 幂等

同一 match_id 和 user_id 的奖励只能结算一次。重复请求只返回已结算结果。
