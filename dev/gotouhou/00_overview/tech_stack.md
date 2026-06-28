# 技术栈

## 客户端

首选 Godot 4.7。

- 语言：GDScript 优先，性能热点可后续使用 C# 或 GDExtension。
- 渲染：2D 批量绘制、对象池、固定逻辑坐标系。
- 网络：Nakama Godot SDK 处理业务 HTTPS RPC/WSS；强实时战斗使用 ECDHE + KCP/UDP + protobuf + ChaCha20-Poly1305，性能热点可通过 GDExtension/C++ 封装。
- 平台：首发 Windows/Linux PC，后续评估 Web 和移动端。
- 文本：Godot 只读取 i18n key 和主题资源，不硬编码“卡牌/符卡”等显示文本。

## 轻量备选

若 Godot 导出包体、弹幕性能或网络层维护成本不满足目标，评估：

- LÖVE2D：Lua 生态轻量，包体小，适合 2D 弹幕。
- raylib：C/C++ 或绑定语言，底层轻量，适合自控渲染管线。

不采用 UE 作为首发引擎，因为它对本项目的 2D 弹幕目标过于臃肿。

## 服务端

- Nakama：账号、会话、业务 RPC、业务 WSS、匹配、房间、排行榜、赛事和存储，是业务服务器核心，不取缔。
- Go Runtime：实现业务逻辑、卡牌/库存/宝箱/奖励、模式资格、匹配编排、battle ticket 签发、战斗结果验签和运营 RPC。
- C++ Battle Server：实现 PVP、Boss、大逃杀等强实时弹幕战斗权威模拟，使用 KCP/UDP、protobuf 和 ChaCha20-Poly1305。
- PhK-Protocol：共享 protobuf schema、业务 envelope、battle ticket、ruleset schema、错误码和代码生成。
- PostgreSQL：持久化卡牌、背包、卡组、掉落、对局、活动和审计。
- Docker Compose：开发环境。

## 通信

- Nakama HTTPS RPC：登录、背包、饰品、道具、卡组、宝箱、任务、排行榜、模式配置、battle ticket 申请。TLS 1.3 之上可叠加应用层 ECC envelope、sign/MAC、seq、timestamp、nonce 和重放保护。
- Nakama WSS：房间、匹配、在线状态、邀请、业务通知、战斗服分配和结算通知，不承载高频弹幕 tick。
- Battle KCP/UDP：战斗输入、卡牌槽位请求、模式动作、服务器快照、对局事件、重连和战斗 Replay 摘要。握手使用 ECDHE，payload 使用 protobuf + ChaCha20-Poly1305。
- 服务间通信：Nakama/Go 与 C++ Battle Server 通过内网 mTLS + gRPC/protobuf 或 HTTP/2/protobuf 交换 match allocation、规则快照、战斗状态摘要和签名结算结果。
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

- 服务端 tick 固定，v0.1 锁定 60 tick/s，客户端 60 FPS 或更高只做渲染；如未来降到 30 tick/s，必须通过新 ruleset/protocol 版本切换。
- 对局内所有随机数来自服务端 seed。
- 客户端不能提交权威状态，只能提交输入意图。
- 战斗核心跨语言迁移后使用定点整数、稳定排序、canonical state hash 和 golden replay 验收，不以 Go/Godot/C++ 各自浮点或 JSON 序列化作为确定性标准。
- Nakama/Go 不再承担高频弹幕模拟的生产热路径；当前 Go/HTTP match MVP 保留为契约测试、迁移对照和本地 fallback。
- C++ Battle Server 不直接发放资产、不改库存、不调用 Steam API；所有资产和奖励经 Nakama/Go 验签入库。
- Steam Web API Key、Inventory 物品策略、市场策略和商业服风控不进入开源仓库。
