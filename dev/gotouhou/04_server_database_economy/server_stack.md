# 服务端技术栈

## 组件

- Nakama：账号、会话、匹配、实时对局、排行榜、赛事。
- Go Runtime：自定义 RPC、权威 match handler、经济逻辑。
- PostgreSQL：持久化业务数据。
- Docker Compose：本地开发。

## Runtime 模块

- `match/`：权威对局。
- `modes/`：考证、大逃杀、世界 Boss、副本 Boss 模式逻辑。
- `cards/`：卡牌定义和效果。
- `economy/`：钱包、奖励、流水。
- `drops/`：宝箱掉落、开箱、概率、保底或 pity 规则。
- `rewards/`：任务、活动、赛季奖励。
- `admin/`：运营配置和审计。

## 环境

开发环境：

- 本地 Nakama。
- 本地 PostgreSQL。
- 测试账号种子数据。
- 本地 Godot 客户端连接 WSS/HTTP。

生产环境：

- Nakama 多实例。
- PostgreSQL 主从或托管服务。
- 日志和监控。
- 内网管理入口。

## 配置

- 所有规则配置带版本号。
- 对局开始时锁定 ruleset_version。
- 卡池、禁卡、奖励活动支持热更新，但不能影响已开始对局。
- Steam Inventory 物品定义、市场属性和官方掉落风控属于闭源 Steam 适配层，不在开源服务端实现。
