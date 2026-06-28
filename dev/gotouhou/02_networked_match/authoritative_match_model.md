# 服务器权威对局模型

## 权威范围

服务器负责：

- 玩家真实位置。
- 弹幕生成和移动。
- 命中、擦弹、Bomb、无敌。
- 卡牌施放和效果。
- 分数、倍率和奖励。
- 对局开始、暂停、结束和结算。

客户端负责：

- 收集输入。
- 播放预测表现。
- 展示服务器快照。
- 播放 UI、音效和特效。

## 对局生命周期

1. 匹配成功。
2. 服务端创建 match seed。
3. 服务端校验双方卡组和版本。
4. 双方进入 loading ready。
5. 服务端开始固定 tick。
6. 客户端上传输入。
7. 服务端广播快照和事件。
8. 时间结束或胜负条件达成。
9. 服务端落库结算并发奖励。

## 大厅到 Battle Server 编排

Nakama/Go Runtime 的大厅阶段只负责业务编排：

1. 客户端通过 `rooms.create`、`rooms.list`、`rooms.get`、`rooms.rules`、`rooms.join` 和 `rooms.leave` 完成房间发现、加入和退出。
2. `rooms.rules` 返回的是规则快照：protocol/ruleset/mode 版本、mode config hash、tick rate、input delay、battle ticket TTL、参与者 deck hash 和 loadout。
3. 房间人数达到模式要求后，Go Runtime 创建 match allocation，选择 C++ Battle Server，并为每个参与者签发短期 battle ticket。
4. 客户端可通过业务 RPC/WSS 接收或显式申请 `battle.allocation` 与 `battle.ticket`，再进入 Battle KCP/UDP。

大厅快照不接受客户端提交权威战斗状态。客户端在大厅阶段可提交的内容仅限模式请求、卡组选择、展示用房间操作和准备/连接意图；位置、弹幕、命中、擦弹、Boss HP、分数、奖励、手牌、冷却和结算结果仍由服务端产生。

多模式对局把卡组和版本校验扩展为模式校验：

- 考证模式校验评级资格和挑战阶段。
- 大逃杀校验人数、公共卡池和回合配置。
- 世界 Boss 校验每日次数、队伍人数和 Boss 当前状态。
- 副本 Boss 校验副本进入条件和队伍人数。

## 禁止事项

- 客户端不能提交分数。
- 客户端不能提交擦弹数。
- 客户端不能提交命中结果。
- 客户端不能提交开箱或掉落结果。
- 客户端不能自行改变卡组快照。
