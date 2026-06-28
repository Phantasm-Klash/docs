# 04 Server Database Economy

本阶段实现服务端、数据库、经济系统、掉落宝箱、奖励、活动和排行榜。所有涉及资产和公平性的结果都由服务端生成并落库。

## 目标

- Nakama + Go Runtime + PostgreSQL 业务开发环境。
- 账号、会话、匹配、房间、业务 WSS 和 C++ Battle Server 战斗分配。
- ECDHE + KCP/UDP + protobuf + ChaCha20-Poly1305 战斗链路。
- 卡牌、背包、卡组、掉落宝箱、奖励和活动。
- 可审计经济流水。

## 原则

- 客户端不直连数据库。
- 经济操作必须幂等。
- 宝箱掉落和开箱结果必须记录 server_seed 和结果。
- 开源版只实现基础库存和非市场化掉落；Steam 商业版通过闭源适配层接入 Steam Inventory 和市场交易。
- 对局奖励必须和 match_id 绑定。
