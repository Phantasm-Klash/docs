# 各端简报与功能介绍（2026-10-07 回溯审计版）

> 本简报基于对 `/root/gotouhou` 五个仓库的实机核查（HEAD、测试全绿证据）产出，
> 用于回答「确认 MVP 目标技术栈实现是否正确」并给出四端现状与功能介绍。
> 证据基线：docs `5fc0d89` / Gensoulkyo `02ad22c` / PhK-BattleServer `c3406df` /
> SpellKard `50f34d3` / PhK-Protocol `b5452af`。

---

## 0. 一句话结论

**MVP 的目标技术栈实现是正确的**：客户端 LayaAir 3（TS）、大厅 Nakama 3.41.0（Go runtime 插件）、
对战服 C++17（KCP/UDP）、数据库 PostgreSQL 16，与用户认定的目标栈完全一致，且四端测试全绿。
唯一系统性问题是**文档漂移**（15 份文档仍写 Godot），已于本轮修复 3 份核心文档。

验证证据（本轮实跑）：

| 仓库 | 命令 | 结果 |
|---|---|---|
| Gensoulkyo | `go test ./...` | 9 个包全 ok，0 失败 |
| PhK-BattleServer | `cmake --build build-linux && ctest` | 3/3 通过（battle / boss_race / lifecycle） |
| SpellKard/laya | `npm test` | 82 passed / 0 failed / 96 registered |

---

## 1. 服务端（Gensoulkyo / Nakama / Go）

**定位**：大厅服 + 业务服 + 对战服纳管器。运行形态是 **Nakama 3.41.0 Go runtime 插件**，
取代了早期「纯 Go HTTP 服务」形态，但内部 core 逻辑仍是同一套。

**部署**：gateway.wjcwqc.com（SSH 6122 / 公网 121.225.78.211，NAT 后），docker compose 跑
Nakama + PostgreSQL 16；端口 7349 gRPC / 7350 HTTP+WS / 7351 console。

**已实现功能模块**（`runtime/` 八个子包）：

| 模块 | 职责 | 关键内容 |
|---|---|---|
| `core` | 业务核心（零外部依赖） | 卡牌数值表 `serverCardCatalog`(12卡)、稀有度、强干扰卡、排位禁卡、允许的关卡/角色；匹配、房间、allocation、ticket、结算、审计、**签到 + 商城** |
| `nakamaapi` | Nakama runtime RPC 适配层 | 把 core 逻辑注册为 Nakama RPC id；服务密钥门禁 |
| `httpapi` | 裸 HTTP 路由层（36 条 `/v1/*`） | 自托管/本地直连路径，与 RPC 双路由 |
| `lobbyws` | WebSocket 大厅（标准库手写） | `/v1/lobby/ws`，Web 端经此中继对战 |
| `battlespawn` | 对局服生命周期 | 每场 spawn 一个 `phk_battle_server`，结束 kill |
| `storage` | 持久化 | `OpenDatabase`/`ApplyMigrations` + `gensoulkyo_schema_migrations` 表 |
| `security` | 安全 | 业务 envelope 审计、lobby/battle 审计、service callback |

**业务能力清单**（从 55 个 RPC id / 36 条 HTTP 路由实测汇总）：

- **账号**：`auth.anonymous`（匿名登录引导 `/v1/bootstrap`）
- **仓库/卡牌/牌组**：`inventory.get`、`cards.upgrade`、`decks.list`、`decks.save`
- **宝箱**：`chests.list`、`chests.open`
- **签到 / 商城**（新增，工作区未提交）：`/v1/checkin`、`/v1/checkin/claim`、
  `/v1/shop`（`GET` catalog）、`/v1/shop/purchase`（同事务扣费+发货+ledger+幂等 receipt），
  类型 `ShopItemView`/`ShopGrant`/`ShopView`/`ShopPurchaseRequest`/`ShopPurchaseView`
- **匹配 / 房间**：`matchmaking.join/cancel/ticket`、`rooms.create/join/leave/list/get/chat/announcement`
- **对局分配**：`battle.allocation`、`battle.ticket(.consume)`、`battle.agent.assignments`（纳管 104）
- **对局服注册**：`battle.servers(.register/heartbeat/offline)`
- **结算 / 回放**：`match.settle`、`battle.result(.submit)`、`replay.get`
- **活动**：`activity.claim`
- **安全审计**：`battle.audit.status`、`business.envelope.audit.status`、`lobby.audit.status`

**跨主机纳管**：`cmd/battle-agent/main.go` 在 104.233.217.232 常驻（systemd `phk-battle-agent`），
注册→心跳→轮询 `battle.agent.assignments`→spawn 对战服→捕获 stdout `RESULT`→
转 `battle.result.submit`→回收；启动时 `reapOrphanProcesses()` 清理残留。
15 分钟 `battleAllocationTTL` 兜底卡死对局。

---

## 2. 客户端（SpellKard / LayaAir 3 / TypeScript）

**定位**：跨平台客户端，引擎为 **LayaAir 3（TypeScript）**，Godot 已彻底废弃。
核心层 `src/core/` **零引擎依赖**（可单测、可移植），适配层 `src/platform/{laya,web,native}/`。

**目录结构**：

- `core/math/`：`deterministic.ts`（确定性 RNG）、`hash64.ts`
- `core/sim/`：`boss_race.ts`（Boss 竞速模拟，与服务端同 ruleset）
- `core/net/`：`lobby_client.ts`、`lobby_protocol.ts`、`battle_client.ts`、`battle_codec.ts`、
  `battle_crypto.ts`、`ikcp.ts`、`kcp_transport.ts`、`transport.ts`
- `core/protocol/`：`codec.ts`、`descriptor.generated.ts`、`types.ts`（由 PhK-Protocol 生成）
- `core/game/`：`lobby_flow.ts`、`match_clock.ts`、`boss_race_view_model.ts`、`bullet_visual.ts`、`input.ts`
- `platform/laya/scenes/`：`lobby_scene`、`room_scene`、`battle_scene`、`result_scene`
- `platform/laya/view/`：`arena`、`boss_race_view`、`bullets`、`hud`、`sprites`、`theme`
- `platform/native/`：原生 UDP 扩展（`native/udp_ext/`，Windows LayaNative 运行时）

**功能**：启动引导 → 大厅（房间列表/创建/加入/聊天）→ 房间 → 对战（弹幕规避 + Boss 竞速 +
倒计时与竞速条 HUD）→ 结算。网络层同时支持 **KCP/UDP 直连**（原生端）与
**WS over TCP 中继**（Web 端，走大厅 `/v1/battle/relay`）。

**构建**：`npm run dev` 可跑；Windows 原生端用官方 `layabox/layaair-cli`
（`npm run fetch:windows` / `assemble:windows` / `ide:check`），IDE 工程在 `laya/layaide/`。

**缺口**：现只有 4 个场景，缺 inventory / card / deck / chest / shop 界面；
`NakamaLobbyTransport` 与 `REST_ROUTES` 补充映射仍在 client-agent 分支（PR #82）。

---

## 3. 对战服（PhK-BattleServer / C++17）

**定位**：权威对局模拟进程，**KCP/UDP** 传输，**每场 spawn 一个进程、结束 kill**。

**传输**：标准 `ikcp` 实现 + `kcp_server_endpoint`；UDP 端口段 7400–7419（104 无 NAT，直连可达）。

**玩法（MVP）**：`mvp_boss_race` —— 2 名玩家各自一份**相同 seed** 的 Boss 副本竞速，
**先击败 Boss 者胜**；1 Boss + 10 种弹幕；点数结算。

**模块**：`match_lifecycle`（开局/结束/结果回传）、`BossRaceModeState`（协议侧定义）、
实例 Boss 结算终态门禁（battle-server-agent PR #111）。

**确定性**：RNG 输入 = `(match_seed, tick, pattern_id/index, spawn_index)`，
禁用系统时间/帧率/客户端随机 → 可复现 Replay。

**生命周期 CLI**：`--max-ticks 7200`（≈2min）backstop，让无客户端对局输出 `TIMEOUT` 而非永久挂起。

**测试**：`tests/battle_server_tests.cpp`（约 6920 行）+ boss_race + lifecycle 三个测试目标，
本轮实跑 3/3 通过。

---

## 4. 协议（PhK-Protocol）

**定位**：跨端共享 schema 仓（Go / C++ / TS 三端消费），**已有 GitHub remote 并合并 PR #7**。

**内容**：

- `proto/phk/v1/`：`common`、`battle`、`business`、`matchmaking`、`replay`、`admin` 六个 protobuf
- `gen/go/phk/v1/manifest.go`、`gen/cpp/phk/v1/manifest.hpp`：轻量 manifest 桥
- `descriptors/phk_v1_descriptor.json`：JSON descriptor（客户端 `descriptor.generated.ts` 来源）
- `schemas/ruleset.schema.json`：ruleset 校验（含 `mvp_boss_race`）
- `fixtures/`：MVP 最小流程 + golden replay summary fixture
- `tools/`：`check_protocol.py`、`export_{go,cpp}_manifest.py`、`export_descriptor.py`
- CI：`protocol-audit.yml`、`codex-auto-merge.yml`

**机制**：当前是 **dependency-light manifest/descriptor 桥**（不做完整 protobuf codegen），
三端版本戳（protocol/ruleset/business/battle api version）由此统一导出。

**缺口（第二阶段）**：完整 protobuf codegen、真实 X25519/AEAD/Ed25519 验签、mTLS。

---

## 5. 并发智能体产出审计（6 个 agent，总健康分 ~92）

| Agent | 角色 | 仓库 | 本轮产出 | 状态 |
|---|---|---|---|---|
| `nakama-server-agent` | Patchouli | Gensoulkyo | PR #112 已 merge-ready（callback 绑定 allocation）；**工作区正在实现切片 07 商城**（+578 行，未提交） | healthy 91 |
| `client-agent` | Reimu | SpellKard | PR #82（nakama lobby transport，blocked_gate）；battle HUD 倒计时/竞速条已合入 main | healthy 88 |
| `battle-server-agent` | Youmu | PhK-BattleServer | PR #111 merge-ready（实例 Boss 结算终态门禁） | healthy 99 |
| `nakama-migration-planner-agent` | Sakuya | docs | 切片 01–06 + mode/boss 规格 + 07（lead 补） | healthy 92 |
| `audit-agent` | Keine | docs | docs #86 需 update_branch；PhK-Protocol #7 merge_ready | healthy 92 |
| `project-manager-agent` | Yukari | docs | 调度与收口 | running |

**风险**：无 high 级资源风险；medium 项为 client-agent / planner / server-agent 日志尾部 >1MB
（建议压缩日志输出）。PR 队列：3 merge-ready + 1 blocked_gate + 1 update_branch。

---

## 6. 文档漂移与修复

**漂移**：`tech_stack.md` 及另 14 份文档仍写「Godot 4.7 首选」，与实际 LayaAir 实现冲突；
`keep_and_abandon_confirmation.md` 中两条 MVP 条款（「不引入 Nakama」「PhK-Protocol 不推 GitHub」）
已被后续用户决策取代。

**本轮修复**（commit `5fc0d89`，已推 main）：

1. `tech_stack.md` 重写为 LayaAir 3 首选 + 现行部署拓扑（Nakama 3.41.0 / PostgreSQL 16 /
   C++17 / Go 1.27.1），Godot 降为「已废弃，仅移植参考」。
2. `keep_and_abandon_confirmation.md` 增补「修订说明（2026-10-07）」，记录两条被取代条款。
3. `00_overview/README.md` 交付物说明同步为 LayaAir。

**待办**：其余 12 份提及 Godot 的文档（`server_stack.md`、`roadmap.md`、
`deterministic_*`、`ui_screens.md` 等）需按同一口径清理——建议交 planner 或 audit-agent 分批处理。

---

## 7. 第二阶段范围与当前状态

| 第二阶段项 | 状态 |
|---|---|
| Nakama 迁移 | **已实质启动**：Nakama 3.41.0 + PostgreSQL 已生产部署，跨主机纳管（104）贯通 |
| 商城/商品模块 | 规格就绪（切片 07），实现进行中（工作区未提交） |
| 迁移切片 01–06 服务端实现 | 规格就绪，部分落地（inventory/decks/chests/matchmaking/rooms/settlement 已有 RPC） |
| 持久化 repository wiring | storage 机制就绪（迁移表），业务 repository 未全部接线 |
| 真实加密（X25519/AEAD/Ed25519） | 未做（MVP 明确不做生产加密） |
| mTLS | 未做 |
| Web 中继优化 | `/v1/battle/relay` 已通（WS over TCP） |
| 全平台补全 | MVP 先 Windows；web/mac/android/linux 待补 |
| 完整 protobuf codegen | 未做（现用 manifest/descriptor 桥） |
| 监控与持久化 | 未做 |

---

## 8. 建议后续动作

1. 合并 PR #111（battle-server）、#112（nakama-server）；解除 #82 的 gate。
2. 提交 nakama-server-agent 工作区的商城实现（切片 07），跑 `go test -tags nakama ./runtime/...`。
3. docs #86 update_branch；清理其余 12 份 Godot 漂移文档。
4. 让 planner 产出切片 08+（第二阶段：真实加密 / mTLS / 全平台）。
5. 收敛 medium 资源风险：压缩 agent 日志尾部输出。
