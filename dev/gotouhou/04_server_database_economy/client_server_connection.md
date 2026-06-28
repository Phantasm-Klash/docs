# 客户端与服务端连接

## 协议

- Nakama HTTPS RPC：登录、资料、饰品、道具、背包、卡组、宝箱、奖励、排行榜、模式配置、battle ticket 申请。
- Nakama WSS：在线状态、房间、匹配进度、邀请、活动通知、战斗服务器分配和结算通知。
- Battle KCP/UDP：实时输入、卡牌槽位请求、模式动作、快照、战斗事件、重连和 Replay 输入流摘要。

业务 RPC/WSS 强制 TLS 1.3。高价值业务写操作叠加应用层 ECC envelope、sign/MAC、seq、timestamp、nonce 和幂等键。战斗层使用 ECDHE 握手、protobuf 编码和 ChaCha20-Poly1305 加密，禁止复用 nonce 和重复 seq。

## 登录流程

1. 客户端启动。
2. 检查本地 session。
3. 无 session 则匿名登录、自建账号登录或平台登录。
4. 获取配置版本。
5. 拉取玩家资料、钱包、卡组和活动。

## 匹配流程

1. 客户端提交 active_deck_id。
2. 客户端提交 mode_id 和可选 mode_params。
3. Nakama/Go 校验卡组、模式资格和规则版本。
4. 加入 Nakama 匹配队列或房间。
5. 匹配成功后，Nakama/Go 分配 C++ Battle Server 并创建 match allocation。
6. Nakama/Go 签发一次性 `battle_ticket`，通过业务 WSS/HTTPS 下发 battle endpoint。
7. 客户端用 battle ticket 连接 Battle KCP/UDP，完成 ECDHE 握手。
8. 所有参与者在业务层和战斗层 ready 后开始 tick。

不同模式人数要求：

- 考证评级：通常 1v1 或单人考证挑战。
- 大逃杀：5-10 人。
- 世界 Boss：4-8 人。
- 副本 Boss：4-8 人。

## 战斗通信

客户端发送：

- input_packet。
- cast_card_request 或 card_slot_request。
- mode_action_request。
- ready。
- reconnect_request。

服务端发送：

- match_start。
- state_snapshot。
- card_event。
- score_update。
- match_end。

战斗结果由 C++ Battle Server 签名提交给 Nakama/Go。Nakama/Go 验证 match id、玩家列表、ruleset_version、结果哈希和幂等键后写入数据库并发放奖励。客户端不能提交伤害、擦弹、命中、排名、Boss 扣血、奖励或结算结果。

## Steam 商业服登录

Steam 商业服登录由闭源适配层处理：

1. 客户端获取 Steam Auth Session Ticket。
2. 官方服务端校验 Steam 身份和 App 所有权。
3. 闭源 Steam 适配层调用 Nakama/Go 映射或创建 Nakama 用户。
4. 未购买游戏的 Steam 账号不能进入官方商业服。

开源服务器不包含 Steam 购买校验，只提供自建账号和基础登录能力。

## 错误处理

- 版本不匹配：要求更新配置或客户端。
- 卡组非法：禁止进入匹配并返回原因。
- 网络异常：进入重连流程。
- 经济操作失败：返回可展示错误码，不允许客户端重试造成重复收益。
