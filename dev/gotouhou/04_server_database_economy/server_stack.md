# 服务端技术栈

## 组件

- Nakama：账号、会话、业务 RPC、业务 WSS、匹配、房间、排行榜、赛事和存储，是业务服务器核心。
- Go Runtime：自定义 RPC、库存/卡组/宝箱/奖励、模式资格、匹配编排、battle ticket 签发、战斗服务分配、战斗结果验签和经济逻辑。
- C++ Battle Server：PVP、Boss、大逃杀等强实时弹幕战斗权威模拟，承载 KCP/UDP、protobuf、ECDHE 和 ChaCha20-Poly1305 战斗会话。
- PhK-Protocol：protobuf schema、业务 envelope、battle ticket、错误码、ruleset schema 和代码生成。
- PostgreSQL：持久化业务数据。
- Docker Compose：本地开发。

## Runtime 模块

- `auth/`：Nakama 登录、会话、非 Steam 开源账号和平台抽象。
- `business_rpc/`：资料、饰品、道具、背包、卡组、宝箱、活动、排行榜和配置 RPC。
- `business_socket/`：房间、匹配进度、邀请、通知、战斗服分配和结算通知。
- `matchmaking/`：模式资格、队列、房间码、玩家快照和战斗分配。
- `battle_ticket/`：一次性 battle ticket 签发、签名、过期、撤销和重放保护。
- `battle_gateway/`：C++ Battle Server 注册、心跳、容量、match allocation、结果验签和审计。
- `modes/`：考证、大逃杀、世界 Boss、副本 Boss 的业务资格、奖励和持久化逻辑；高频 tick 机制在 C++ Battle Server 执行。
- `cards/`：卡牌定义和效果。
- `economy/`：钱包、奖励、流水。
- `drops/`：宝箱掉落、开箱、概率、保底或 pity 规则。
- `rewards/`：任务、活动、赛季奖励。
- `admin/`：运营配置和审计。

## 环境

开发环境：

- 本地 Nakama。
- 本地 PostgreSQL。
- 本地 C++ Battle Server。
- 本地 PhK-Protocol schema/codegen。
- 测试账号种子数据。
- 本地 Godot 客户端连接 Nakama WSS/HTTPS 和 Battle KCP/UDP。

生产环境：

- Nakama 多实例。
- C++ Battle Server 多实例，按房间/模式分配。
- PostgreSQL 主从或托管服务。
- 内网 mTLS 服务发现、健康检查和容量上报。
- 日志和监控。
- 内网管理入口。

## 配置

- 所有规则配置带版本号。
- 对局开始时锁定 ruleset_version。
- 卡池、禁卡、奖励活动支持热更新，但不能影响已开始对局。
- battle ticket 绑定 protocol_version、ruleset_version、deck_snapshot_hash、mode_config_hash、battle_server_id 和过期时间。
- C++ Battle Server 不直接改资产；结算结果必须由 Nakama/Go 验签、幂等入库和发奖。
- Steam Inventory 物品定义、市场属性和官方掉落风控属于闭源 Steam 适配层，不在开源服务端实现。
