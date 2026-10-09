# 技术栈

> 修订说明（2026-10-07）：客户端引擎已由 Godot 变更为 **LayaAir 3（TypeScript）**
> （见 `keep_and_abandon_confirmation.md`）。本文件为权威技术栈声明，改版后各阶段文档
> 如有冲突以本文件 + `keep_and_abandon_confirmation.md` 为准。

## 客户端

**首选 LayaAir 3（TypeScript）**，仓库路径 `SpellKard/laya/`。

- 语言：TypeScript（严格模式）；核心层 `src/core/` 零引擎依赖，便于跨端复用与 Node 测试。
- 渲染：LayaAir 3 2D 批量绘制、对象池、固定逻辑坐标系。
- 平台适配：`src/platform/{laya,web,native}/` 分层；Web 端走浏览器 Canvas，
  原生端走 Layanative（Windows 运行时已可下载，支持 MSVC 工程）。
- 网络：
  - 业务：Nakama HTTPS RPC + WSS（session token 认证）。
  - 实时战斗：ECDHE + KCP/UDP + protobuf + ChaCha20-Poly1305；
    Web 端因浏览器无法直连裸 UDP，**经大厅服 WebSocket 中继**。
  - 原生端通过 `native/udp_ext/` 扩展做真 UDP。
- 平台：MVP 首发 Windows + Web；后续 mac/linux/android（第二阶段）。
- 文本：只读取 i18n key 和主题资源，不硬编码「卡牌/符卡」等显示文本。

## 已废弃 / 仅移植参考

- **Godot 4.7 + GDScript**：曾是首选引擎，2026-10-06 被 LayaAir 3 全面替换。
  `SpellKard/godot/` 目录仍在仓库中，**仅作弹幕/数学/Boss 逻辑的移植参考**，
  待 C++ 与 LayaAir 落地后移除。不再作为任何新功能的实现载体。
- LÖVE2D / raylib 备选：不再评估（LayaAir 已满足需求）。
- 不采用 UE：对 2D 弹幕目标过于臃肿。

## 服务端

- **Nakama 3.41.0**：账号、会话、业务 RPC、业务 WSS、匹配、房间、排行榜、赛事和存储，
  是业务服务器核心。运行形态：Go runtime plugin（`heroiclabs/nakama-pluginbuilder:3.41.0`，
  Go 1.27.1，`-trimpath` 构建）。
- **Go Runtime（Gensoulkyo）**：业务逻辑、卡牌/库存/宝箱/奖励、模式资格、匹配编排、
  battle ticket 签发、战斗结果验签和运营 RPC。`go 1.27.1`，`nakama-common v1.48.0`。
- **C++ Battle Server（PhK-BattleServer）**：PVP、Boss、大逃杀等强实时弹幕战斗权威模拟，
  C++17，使用 KCP/UDP、protobuf 和 ChaCha20-Poly1305。
- **PhK-Protocol**：共享 protobuf schema、业务 envelope、battle ticket、ruleset schema、
  错误码和代码生成。当前用 dependency-light manifest/descriptor 桥，
  **完整 protobuf Go/C++/客户端 codegen 待第二阶段落地**。
- **PostgreSQL 16**：持久化卡牌、背包、卡组、掉落、对局、活动和审计。
  当前 `runtime/storage` 已有连接/迁移机制与 `001_business_security_audit` 迁移；
  **业务 repository wiring 待第二阶段落地**（业务状态目前仍在 core 内存）。
- **Docker Compose**：开发与部署环境（`Gensoulkyo/deployments/nakama/`）。

## 通信

- **Nakama HTTPS RPC**：登录、背包、饰品、道具、卡组、宝箱、任务、排行榜、模式配置、
  battle ticket 申请。TLS 1.3 之上可叠加应用层 ECC envelope、sign/MAC、seq、timestamp、
  nonce 和重放保护。调用姿势：`POST /v2/rpc/<id>?unwrap=true`，body 为 JSON 字符串（double-encoded）。
- **Nakama WSS**：房间、匹配、在线状态、邀请、业务通知、战斗服分配和结算通知，
  不承载高频弹幕 tick。
- **Battle KCP/UDP**：战斗输入、卡牌槽位请求、模式动作、服务器快照、对局事件、重连和
  战斗 Replay 摘要。握手使用 ECDHE，payload 使用 protobuf + ChaCha20-Poly1305。
  客户端**直连对战服 UDP**（对战服在独立主机时需宿主转发 UDP 端口段）；
  Web 端经大厅 WS 中继。
- **服务间通信**：Nakama/Go 与 C++ Battle Server 通过内网 mTLS + gRPC/protobuf 或
  HTTP/2/protobuf 交换 match allocation、规则快照、战斗状态摘要和签名结算结果。
  MVP 阶段暂用共享服务密钥（`X-Gensoulkyo-Service-Key`）替代 mTLS。
- 客户端不直连数据库。

## 部署拓扑（现行）

- **gateway.wjcwqc.com（SSH 6122，公网 121.225.78.211，NAT 后）**：
  Nakama + PostgreSQL（docker compose），端口 7349 gRPC / 7350 HTTP+WS / 7351 console。
- **104.233.217.232（SSH 65323，独立公网 IP）**：`phk-battle-agent`（systemd，`Restart=always`）
  + 按需 spawn 的 `phk_battle_server` 进程池（UDP 7400–7419）。
- 客户端 → 121.225.78.211:7350（大厅 HTTP/WS）；对战直连 104 UDP。

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

- 服务端 tick 固定，v0.1 锁定 60 tick/s，客户端 60 FPS 或更高只做渲染；
  如未来降到 30 tick/s，必须通过新 ruleset/protocol 版本切换。
- 对局内所有随机数来自服务端 seed。
- 客户端不能提交权威状态，只能提交输入意图。
- 战斗核心跨语言迁移后使用定点整数、稳定排序、canonical state hash 和 golden replay 验收，
  不以 Go/LayaAir/C++ 各自浮点或 JSON 序列化作为确定性标准。
- Nakama/Go 不再承担高频弹幕模拟的生产热路径；当前 Go/HTTP match MVP 保留为契约测试、
  迁移对照和本地 fallback。
- C++ Battle Server 不直接发放资产、不改库存、不调用 Steam API；所有资产和奖励经
  Nakama/Go 验签入库。
- Steam Web API Key、Inventory 物品策略、市场策略和商业服风控不进入开源仓库。
