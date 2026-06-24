# 技术栈

## 客户端

首选 Godot 4.7。

- 语言：GDScript 优先，性能热点可后续使用 C# 或 GDExtension。
- 渲染：2D 批量绘制、对象池、固定逻辑坐标系。
- 网络：Nakama Godot SDK，HTTPS 处理账号和经济，WSS 处理实时对局。
- 平台：首发 Windows/Linux PC，后续评估 Web 和移动端。
- 文本：Godot 只读取 i18n key 和主题资源，不硬编码“卡牌/符卡”等显示文本。

## 轻量备选

若 Godot 导出包体、弹幕性能或网络层维护成本不满足目标，评估：

- LÖVE2D：Lua 生态轻量，包体小，适合 2D 弹幕。
- raylib：C/C++ 或绑定语言，底层轻量，适合自控渲染管线。

不采用 UE 作为首发引擎，因为它对本项目的 2D 弹幕目标过于臃肿。

## 服务端

- Nakama：账号、会话、匹配、实时房间、排行榜、赛事和存储。
- Go Runtime：实现权威对局、卡牌、掉落宝箱、奖励和运营 RPC。
- PostgreSQL：持久化卡牌、背包、卡组、掉落、对局、活动和审计。
- Docker Compose：开发环境。

## 通信

- HTTPS RPC：登录、背包、卡组、宝箱、任务、排行榜。
- WSS Match：输入上报、卡牌请求、服务器快照、对局事件。
- 客户端不直连数据库。

## Steam 闭源适配

Steam 商业发行版额外接入：

- Steamworks SDK。
- Steam Session Ticket 和 Web API 所有权校验。
- Steam Stats and Achievements。
- Steam Workshop/UGC。
- Steam Inventory Service。
- Steam 市场可交易物品配置。

这些内容放在闭源适配层，开源版通过平台抽象接口使用空实现或本地实现。

## 关键约束

- 服务端 tick 固定，建议首版 30 tick/s，客户端 60 FPS 渲染。
- 对局内所有随机数来自服务端 seed。
- 客户端不能提交权威状态，只能提交输入意图。
- Steam Web API Key、Inventory 物品策略、市场策略和商业服风控不进入开源仓库。
