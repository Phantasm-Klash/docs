# 客户端与服务端连接

## 协议

- HTTPS RPC：登录、资料、背包、卡组、宝箱、奖励、排行榜。
- WSS Match：实时输入、卡牌请求、快照、事件和结算。

## 登录流程

1. 客户端启动。
2. 检查本地 session。
3. 无 session 则匿名登录、自建账号登录或平台登录。
4. 获取配置版本。
5. 拉取玩家资料、钱包、卡组和活动。

## 匹配流程

1. 客户端提交 active_deck_id。
2. 客户端提交 mode_id 和可选 mode_params。
3. 服务端校验卡组、模式资格和规则版本。
4. 加入对应模式匹配队列。
5. 匹配成功后创建权威 match。
6. 所有参与者 ready 后开始 tick。

不同模式人数要求：

- 考证评级：通常 1v1 或单人考证挑战。
- 大逃杀：5-10 人。
- 世界 Boss：4-8 人。
- 副本 Boss：4-8 人。

## 对局通信

客户端发送：

- input_packet。
- cast_card_request。
- mode_action_request。
- ready。
- reconnect_request。

服务端发送：

- match_start。
- state_snapshot。
- card_event。
- score_update。
- match_end。

## Steam 商业服登录

Steam 商业服登录由闭源适配层处理：

1. 客户端获取 Steam Auth Session Ticket。
2. 官方服务端校验 Steam 身份和 App 所有权。
3. 校验通过后映射或创建 Nakama 用户。
4. 未购买游戏的 Steam 账号不能进入官方商业服。

开源服务器不包含 Steam 购买校验，只提供自建账号和基础登录能力。

## 错误处理

- 版本不匹配：要求更新配置或客户端。
- 卡组非法：禁止进入匹配并返回原因。
- 网络异常：进入重连流程。
- 经济操作失败：返回可展示错误码，不允许客户端重试造成重复收益。
