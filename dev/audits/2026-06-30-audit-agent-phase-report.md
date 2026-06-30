# audit-agent 阶段审计报告

审计时间：2026-06-30 10:34 UTC

## 总体判断

- docs/dev 主线未变：项目仍约 38%，当前主线是 Phase 3 服务器权威在线 MVP 与服务拆分收敛；Phase 2/6/8 的客户端、UI、Boss 模式切片并行补齐。
- 服务端方向整体健康：Gensoulkyo #21 已合并为 `23065df`，完成 Nakama business room contract 对齐；PhK-BattleServer #18 仍打开但 `CLEAN` 且 required checks 通过，方向符合 Boss 结算字段、战斗服结果防篡改和 docs/dev 的服务器权威路线。
- docs #28 仍打开且 `CLEAN`，checks 通过；该 PR 增加 agent resource risk 汇总，符合三小时邮件短化和 token 风险可见化要求。
- 最高版本流风险仍是 SpellKard：open PR #13-#19 共 7 个，4 个 `DIRTY`、3 个 `BEHIND`，且根仓 `main...origin/main [ahead 34]`、client persistent worktree `ahead 16`。
- Gensoulkyo 根仓仍有旧 `agent/gensoulkyo-lobby/20260629-0900` dirty 4；nakama persistent worktree 当前相对远端 `ahead 1, behind 1`，说明 #21 合并和远端分支重建后需要同步，audit-agent 不应回滚。nakama-server-agent 最新运行因账号并发限制失败，属于系统容量/调度风险，不是代码测试失败。
- 旧 agent 身份 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 应继续冻结；只把已证明有价值的提交吸收到五个新 agent 的 fresh 分支或 PR。

## 仓库状态

- `docs`：当前工作在 `agent/audit-agent/resource-risk-20260630-1022`，PR #28 `Summarize agent resource risk` 打开且 `CLEAN`，`docs-audit` 与 `auto-merge` 通过。本轮追加审计报告并合并最新 `origin/main`，避免 #29 合并后 PR 落后。
- `SpellKard`：根仓 `main...origin/main [ahead 34]` 且干净；client-agent persistent worktree `agent/client-agent/persistent...origin/agent/client-agent/persistent [ahead 16]`。最新 client final 记录新增 Replay 验证筛选、Replay 索引收藏/移除操作和 i18n/headless 覆盖，但尚未推送或新开 PR。
- `Gensoulkyo`：根仓在旧 `agent/gensoulkyo-lobby/20260629-0900`，有 `cmd/gensoulkyo_nakama` 相关 dirty 4。PR #21 已于 2026-06-30 10:24 UTC 合并，merge commit `23065df`；persistent worktree 需要与远端重建状态对齐。
- `PhK-BattleServer`：根仓仍在旧 `agent/phk-battle-server/20260629-0030` 且干净。battle-server persistent 分支提交 `9e487f9` 已推送，PR #18 打开且 `CLEAN`，checks 通过；battle-server-agent 最新轮已正常完成。
- `PhK-Protocol`：`main...origin/main` 干净，open PR 为 0；仍需把临时 manifest/JSON bridge 收敛为真实 protobuf Go/C++/Godot 生成物。

## PR 与版本风险

- docs #28：`CLEAN`，`docs-audit` / `auto-merge` 通过；本轮继续使用该 PR 承载审计报告更新。
- PhK-BattleServer #18：`CLEAN`，`battle-server-checks` / `auto-merge` 通过；等待合并。变更把 `boss_defeated_tick` 绑定到服务器最终快照，tamper 返回 `boss_defeated_tick_mismatch`。
- Gensoulkyo #21：已合并，`server-contract-tests` / `auto-merge` 通过；变更覆盖 battle ticket consume 生命周期回执和 BusinessEvent 安全合同。
- SpellKard #13/#15/#16/#18：`DIRTY`，需要冲突解决，或由 fresh persistent PR 明确 supersede 后关闭。
- SpellKard #14/#17/#19：`BEHIND`，需要更新到最新 main、重跑 checks 后评审，或由 fresh PR 明确 supersede。
- 当前 open PR 事实：docs 1、SpellKard 7、PhK-BattleServer 1；Gensoulkyo 0、PhK-Protocol 0。

## Agent 采样

- `client-agent`：运行中；上轮完成 Replay verification filters 与 Replay index actions，验证 `tools/ci_static_checks.py`、client smoke、client UI smoke、Boss pattern headless 全部通过。风险是 persistent 分支累计 ahead 16，必须先推 fresh PR 或拆分，不宜继续扩大 UI/Boss 新功能面。
- `battle-server-agent`：已完成；上轮合并 #17，新增 #18；验证 `python3 tools/check_battle_server.py`、`docker-compose run --rm test`、`protocol_audit_check.py` 通过。host 缺 `cmake`，Docker 路径已覆盖 CMake/CTest。
- `nakama-server-agent`：最新运行失败，日志尾部为并发限制 `Concurrency limit exceeded for account`；但本轮有效工作 #21 已合并，且此前验证 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py` 通过。下一步应由 manager 重启后同步 persistent，继续 PostgreSQL wiring 或生产 S2S/crypto，而不是继续使用旧 dirty lobby 分支。
- `audit-agent`：本轮刷新阶段审计报告和邮件正文，补齐 #18/#21 最新状态与资源风险。
- `project-manager-agent`：已完成；已合并 docs #29，把 PR queue 增加 `owner_agent` / `action_category` 路由，brief 邮件会显示责任 agent 和动作类型。下一轮应优先协调 SpellKard 队列收敛和 persistent 分支同步。

## 测试证据

- 最新全局回归摘要：2026-06-30T09:00:24Z，`ok=true`、`failed=0`、`ignored=0`。
- 全局摘要包含 SpellKard Godot headless UI/Boss 检查、跨仓 `protocol_audit_check.py`、Gensoulkyo 与 PhK-BattleServer `docker-compose config`；docker 与 `docker-compose` 均可用。
- #21 服务端合并前有 `server-contract-tests` 通过；#18 战斗服 PR 有 `battle-server-checks` 通过。
- 本轮 audit-agent 只改 docs 审计报告和 `.agents` 邮件正文，不改协议、网络、匹配、战斗服、鉴权或安全代码，因此不触发额外 protocol audit。

## Token 与停滞风险

- 资源风险已进入邮件正文：battle-server-agent 与 project-manager-agent high，client-agent / nakama-server-agent / legacy-agent-roster medium。
- battle-server-agent 最新轮约 `552,902` tokens；下一轮必须小切片化，报告只保留命令级验证证据。
- project-manager-agent 最新轮约 `638,233` tokens；下一轮也应短化为队列收敛和必要 merge，不再展开大段日志。
- nakama-server-agent 最新轮约 `309,151` tokens，且因账号并发限制失败；需要 manager 在容量恢复后重启，不应把失败误判为代码回归。
- client-agent persistent ahead 16，且运行日志超过 1MB；即使当前 token 样本未落盘，合并风险仍高。
- 停滞风险主要来自旧 dirty worktree、旧 PR 队列、本地 ahead 分支，以及并发限制导致的 agent 重启失败。

## 下一步

- project-manager-agent：把 SpellKard #13-#19 转成可执行清退表；要求 client-agent 用一个 fresh PR 证明覆盖，或逐个关闭/supersede。
- client-agent：暂停新 UI/Boss 功能扩张，先把 `agent/client-agent/persistent` 的 16 个提交推送成可 review PR，并标注旧 PR 的覆盖关系。
- nakama-server-agent：等待 manager 在并发容量恢复后重启；同步 #21 合并后的 persistent 分支，继续 PostgreSQL 持久化或生产 S2S auth/crypto；旧 `gensoulkyo-lobby` dirty 4 只能吸收或废弃，不应直接合并。
- battle-server-agent：等待 #18 合并后继续 protobuf C++ 绑定、真实 Ed25519 ticket/result 验签、X25519/KCP/AEAD 替换；涉及协议/战斗服继续跑 `docker-compose` 与 protocol audit。
- audit-agent：继续短中文审计 PR、dirty work、测试证据、旧 agent 清退与 token 风险；三小时邮件正文优先使用本报告短版。
