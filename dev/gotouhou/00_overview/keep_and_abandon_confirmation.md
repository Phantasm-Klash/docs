# 保留与放弃确认（MVP 重写范围）

状态更新时间：2026-10-06

本文件确认本次「可交互最低实现（MVP）」重写中，现有代码与设计哪些**保留**、哪些**放弃（推迟到第二阶段）**、哪些**降级**、哪些**重写/新建**。与 `network_security_and_server_split_plan.md` 的迁移清单配套使用；发生冲突时以本文件为准。

## 决策结论

- 服务端拆分方向不变：**业务/大厅后端 + 独立对局后端 + 共享协议仓**，但 MVP 阶段不引入 Nakama。
- 客户端引擎：**Godot 全面替换为 LayaAir 3（TypeScript）**，MVP 即用 LayaAir，直接替换 `SpellKard/godot`。
- 战斗传输：**对局服使用 KCP/UDP**；Web 端因浏览器无法直连裸 UDP，**经大厅服 WebSocket 中继**。
- 网络拓扑：客户端先连**大厅服**（确认房间与玩家信息）→ 开局时大厅**创建对局服并下发连接信息** → 客户端连**对局服**进入战斗页。
- 对局服生命周期：**每场对局 spawn 一个 C++ 对局服进程，结束即 kill 回收**。
- 胜负模型：**两名玩家各自一份相同 seed 的 Boss 副本竞速**，先击败自己的 Boss 者获胜并结算点数。
- 内容规模：1 个 Boss + 10 种弹幕机制 + 2 名玩家。
- 「放弃」项**不立即删除**，统一推迟到 **MVP 之后的第二阶段**，与 LayaAir 全量迁移一起处理。

## 保留（继续使用）

- `PhK-Protocol` 的 proto schema、ruleset schema、导出工具与 fixtures —— 唯一协议契约来源（**仅本地版本控制，不推 GitHub**）。
- `Gensoulkyo/runtime/core` 的业务逻辑：账号、session、bootstrap、库存、卡组、宝箱、活动、排行榜、匹配、房间、结果幂等。
- `Gensoulkyo/runtime/core/simulation.go` 的确定性模拟与 seed 机制 —— 作为 C++ 移植基准与 golden 对照。
- 设计约束文档：`docs/dev/gotouhou/02_networked_match/**`（确定性模拟、权威模型、快照、输入同步）。
- 三端版本戳常量与字段门禁。
- 开源/闭源边界 `open_source_boundary.md`。
- `SpellKard` 的弹幕/数学/Boss 逻辑（`bullet_math.gd`、`bullet_pattern_library.gd`、`boss_spellbook_model.gd`）—— **仅作为移植参考，C++ 落地后随 `godot/` 一并移除**。

## 放弃（推迟到第二阶段，不立即删除）

- Nakama 适配骨架：`Gensoulkyo/runtime/nakamaapi`、`cmd/gensoulkyo_nakama`。
- 业务 envelope 加密脚手架：`Gensoulkyo/runtime/security` 的 `X-PhK-Business-*`。
- KCP echo 占位：`PhK-BattleServer/include/phk/battle/kcp_endpoint.hpp`。
- 假握手 / 假密钥：`PhK-BattleServer/src/handshake.cpp`。
- 客户端战斗加密脚手架：`battle_network_client_model.gd`。
- 空目录 `D:/gotouhou/godot/`。
- 把 KCP + ECDHE + ChaCha20 全量生产加密作为 MVP 目标（MVP 用轻量校验，生产加密推迟）。

## 降级

- Gensoulkyo 高频战斗模拟：生产权威 → 测试 fixture / 本地 fallback / golden 对照。
- Gensoulkyo HTTP MVP：生产架构 → 契约测试 / 本地开发 fallback。
- 手写 Go/C++ struct 镜像 proto：过渡桥（第二阶段换生成绑定）。
- SpellKard 联机部分：本地权威 → 被 LayaAir 客户端整体替换。

## 重写 / 新建

- **PhK-BattleServer（C++）**：KCP listener + 权威 tick loop + 10 种弹幕 + 1 Boss + 2P 胜负 + 结算 + 结果回传 + 生命周期。
- **Gensoulkyo（Go）**：WebSocket 承载大厅/房间/匹配/开局/结果通知 + 对局服生命周期（spawn/reap）+ 结果接收 + Web 端 WS 中继。
- **SpellKard（LayaAir / TypeScript）**：替换 `godot/`，新增大厅/房间/匹配/战斗/结算 + KCP 客户端 + 原生 UDP 扩展。
- **CI/CD**：`gateway.wjcwqc.com:6122` 编译部署 + GitHub Actions 校验/审计/发版。

## 第二阶段范围（MVP 之后）

- 处理全部「放弃」项：Nakama 迁移、业务 envelope、真实 X25519/AEAD/Ed25519 验签、mTLS。
- Web 中继优化（WebTransport/WebRTC）、全平台补全（mac/linux/android）。
- 完整 protobuf Go/C++/客户端 codegen，替换手写 struct 与 manifest 桥。
- 持久化（PostgreSQL repository wiring）与生产部署监控。

## 验收标准

- 任何新增代码都能对照本文件判断：属于保留、放弃、降级还是重写。
- MVP 阶段不引入 Nakama、不做生产加密、不删除「放弃」清单中的文件。
- `PhK-Protocol` 不再向 GitHub 推送。
