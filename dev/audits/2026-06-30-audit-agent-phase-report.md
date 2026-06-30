# audit-agent 阶段审计报告

审计时间：2026-06-30 11:01 UTC

## 总体判断

- docs/dev 主线未变：项目仍约 38%，当前主线是 Phase 3 服务器权威在线 MVP 与服务拆分收敛；Phase 2/6/8 的客户端、UI、Boss 模式切片并行补齐。
- 服务端方向继续健康推进：Gensoulkyo #22 打开且 `CLEAN`，覆盖 settlement business event alias 与 player-scoped service callback guard；PhK-BattleServer #18 打开且 `CLEAN`，继续加强 Boss result/replay 投影验真。两者都符合 Nakama 业务服 + C++ Battle Server 的服务器权威路线。
- docs 方向在补管理闭环：#28 承载 audit-agent 资源风险报告，#30 承载 project-manager-agent 的 stale PR supersede group 摘要；两个 PR 都 `CLEAN` 且 required checks 通过。
- 最高版本流风险仍是 SpellKard：open PR #13-#19 共 7 个，4 个 `DIRTY`、3 个 `BEHIND`；根仓 `main...origin/main [ahead 34]`，client-agent final 显示 persistent 分支已领先 21 个提交。下一步应停止扩新功能，先用 fresh current-base PR 或逐项 supersede/close 清队列。
- Gensoulkyo 根仓仍在旧 `agent/gensoulkyo-lobby/20260629-0900` 且有 `cmd/gensoulkyo_nakama` dirty 4；这些改动不得由 audit-agent 回滚，应由 nakama-server-agent 吸收、重建或废弃。
- 旧 agent 身份 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 应继续冻结；只迁移已证明有价值的提交到五个新 managed agents。

## 仓库状态

- `docs`：当前分支 `agent/audit-agent/resource-risk-20260630-1022` 干净，PR #28 `Summarize agent resource risk` 打开且 `CLEAN`。另有 project-manager-agent PR #30 `Surface stale PR supersede groups` 打开且 `CLEAN`。
- `SpellKard`：根仓 `main...origin/main [ahead 34]` 且干净；client-agent final 显示 `agent/client-agent/persistent` 领先远端 21 个提交，新增 Boss slot layout/status/page-spec 切片但未开 PR。
- `Gensoulkyo`：根仓在旧 `agent/gensoulkyo-lobby/20260629-0900`，有 `cmd/gensoulkyo_nakama/README.md`、`module.go`、`module_source_test.go` 和新增 `module_nakama_test.go` 未提交。PR #22 已打开并通过 checks。
- `PhK-BattleServer`：根仓仍在旧 `agent/phk-battle-server/20260629-0030` 且干净。battle-server-agent 已把 transfer-card、friendly-fire、boss max hp result projection 推入 PR #18。
- `PhK-Protocol`：`main...origin/main` 干净，open PR 为 0；仍需把临时 manifest/JSON bridge 收敛为真实 protobuf Go/C++/Godot 生成物。

## PR 与版本风险

- 当前 open PR 数：11。
- docs #28：`CLEAN`，`docs-audit` / `auto-merge` 通过；本轮继续使用该 PR 承载审计报告更新。
- docs #30：`CLEAN`，`docs-audit` / `auto-merge` 通过；新增 stale PR group 摘要能力，方向正确，等待合并。
- Gensoulkyo #22：`CLEAN`，`server-contract-tests` / `auto-merge` 通过；等待合并，下一步适合接 tag-build CI 或 PostgreSQL/service callback 持久化。
- PhK-BattleServer #18：`CLEAN`，`battle-server-checks` / `auto-merge` 通过；等待合并，下一步才进入真实 Ed25519/X25519/KCP/protobuf/AEAD。
- SpellKard #13/#15/#16/#18：`DIRTY`，需要冲突解决或由 current-base fresh PR 明确 supersede。
- SpellKard #14/#17/#19：`BEHIND`，需要更新分支、重跑 checks、评审，或由 fresh PR 明确 supersede。

## Agent 采样

- `client-agent`：运行中；最新 final 完成 Boss 站位 layout 元数据与 status/page-spec 投影，验证 `tools/ci_static_checks.py`、client smoke、Boss catalog、client UI smoke 通过。风险是 ahead 21 和旧 PR 堆积。
- `battle-server-agent`：运行中；最新 final 完成 Boss transfer-card、friendly-fire policy、boss max hp result projection，并跑通 `python3 tools/check_battle_server.py`、`docker-compose run --rm test`、`protocol_audit_check.py`。
- `nakama-server-agent`：运行中；最新 final 完成 settlement alias 与 player-scoped service callback guard，跑通 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py`，PR #22 等待合并。
- `project-manager-agent`：运行中；最新 final 完成 `supersede_groups` 与 brief mail wording 修复，docs #30 等待合并。
- `audit-agent`：本轮刷新阶段审计报告和邮件正文，重点更新 #22/#30、SpellKard ahead 21 与 11 个 open PR 事实。

## 测试证据

- 最新全局回归摘要：2026-06-30T09:00:24Z，`ok=true`、`failed=0`、`ignored=0`。
- 全局摘要包含 SpellKard Godot headless UI/Boss 检查、跨仓 `protocol_audit_check.py`、Gensoulkyo 与 PhK-BattleServer `docker-compose config`；docker 与 `docker-compose` 均可用。
- #22 服务端 PR 有 `server-contract-tests` 与 `auto-merge` 通过；#18 战斗服 PR 有 `battle-server-checks` 与 `auto-merge` 通过；docs #28/#30 均有 `docs-audit` 与 `auto-merge` 通过。
- 本轮 audit-agent 只改 docs 审计报告和 `.agents` 邮件正文，不改协议、网络、匹配、战斗服、鉴权或安全代码，因此不触发额外 protocol audit。

## Token 与停滞风险

- 资源风险仍偏高：battle-server-agent high，client-agent high；audit-agent、project-manager-agent、nakama-server-agent 与 legacy roster medium。
- battle-server-agent 上轮约 829k tokens 且日志约 3.2MB，必须停止把长日志复制进报告，只保留命令级验证证据。
- client-agent 上轮约 592k tokens，且当前 ahead 21；必须拆 fresh PR，不宜继续扩大 UI/Boss 功能面。
- audit-agent 与 project-manager-agent 都超过 200k tokens；后续报告应保持短中文、只列事实和行动。
- 停滞风险主要来自旧 dirty worktree、旧 PR 队列、本地 ahead 分支，以及 ready PR 合并速度慢于 agent 产出速度。

## 下一步

- project-manager-agent：推动 docs #30 合并后，让 manager summary 正式输出 stale group；继续把 SpellKard #13-#19 转成可执行清退表。
- client-agent：先处理 SpellKard stale group 和 ahead 21，开 fresh current-base PR 或逐项记录 supersede/close 依据，再继续 Boss/Replay/UI 功能。
- nakama-server-agent：合并 #22 后同步工作树，优先 tag-build CI、service-origin result/ticket 回调持久化或 PostgreSQL repository wiring。
- battle-server-agent：合并 #18 后再推进 protobuf C++ 绑定、真实 Ed25519 ticket/result 验签、X25519/KCP/AEAD。
- audit-agent：继续短中文审计 PR、dirty work、测试证据、旧 agent 清退与 token 风险；三小时邮件正文优先使用本报告短版。
