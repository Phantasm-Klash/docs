# Nakama 迁移切片规格

本目录把 Gensoulkyo 当前业务实现迁移到 Nakama Runtime + Nakama
storage 的工作拆成可独立实现、可回滚的小切片。每个切片必须写明：

- RPC/WSS id、输入输出类型、storage collection/key 和 leaderboard；
- 客户端接入点与兼容期行为；
- 从当前 Gensoulkyo `userState` 或导出快照迁移到 Nakama 的步骤；
- 双读、双写、切换和回滚条件；
- 服务端、客户端、协议审计的最小验收命令。

切片只规划业务边界，不实现客户端、战斗服或 Nakama 业务代码。高频战斗
tick、战斗结果签名回调和奖励结算仍由各自 owning agent 负责。

当前顺序：

1. `01-login-and-bootstrap.md`：账号/会话映射和 bootstrap 聚合读取。
2. `02-inventory-and-decks.md`：钱包、卡牌库存、卡组和卡组并发保存。

