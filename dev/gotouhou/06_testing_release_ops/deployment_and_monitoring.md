# 部署与监控

## 开发部署

- Docker Compose 启动 Nakama 和 PostgreSQL。
- 本地 Godot 连接开发服。
- 使用 seed 数据创建测试账号、卡牌和宝箱池。

## 测试服

- 独立数据库。
- 独立 ruleset_version。
- 开启详细日志。
- 允许 GM 工具和调试面板。

## 生产服

- Nakama 多实例。
- PostgreSQL 备份。
- 日志集中收集。
- 管理入口内网限制。
- 灰度发布。

## 监控指标

- match_count。
- match_count_by_mode。
- active_players。
- tick_duration_ms。
- database_latency_ms。
- websocket_disconnect_rate。
- chest_open_error_rate。
- reward_duplicate_attempts。
- cheat_suspicion_count。
- rating_percentile_job_lag。
- boss_hp_update_failures。
- battle_royale_round_timeout_count。

## 告警

- tick 超时。
- 数据库连接异常。
- 开箱失败率上升。
- 对局断线率上升。
- 奖励重复请求激增。
- Boss 血量扣除失败或世界通告重复。
- 大逃杀回合超时异常。
- 评级前 30% 计算任务延迟。

## 备份

数据库至少每日备份。开箱和经济流水属于高优先级恢复数据。Steam 商业服还需要对接 Steam Inventory 发放日志和市场相关审计。
