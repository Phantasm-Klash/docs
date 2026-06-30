# audit-agent 状态与风险审计

审计时间：2026-06-30T12:36:00Z

## 结论

- docs/dev 方向未变：主线仍是 Phase 3 服务器权威在线 MVP，继续收敛协议 v0.1、Nakama/Go 业务服、C++ Battle Server、PostgreSQL 持久化和正式 Godot UI。
- 当前 5 个 managed agents 均为 running；最新 dry-run 采样 `actions=0`、`started=0`，没有 failed/blocked agent。client-agent、battle-server-agent、nakama-server-agent 在上一轮已完成并写 final 日志，随后已被 supervisor 重新拉起。
- 当前 open PR 共 9 个：SpellKard 7 个、Gensoulkyo 1 个、PhK-BattleServer 1 个；docs 与 PhK-Protocol 无 open PR。
- 最高版本流风险仍是 SpellKard：7 个旧 PR 组成 stale group，其中 #13/#15/#16/#18 为 `DIRTY`，#14/#17/#19 为 `BEHIND`；根仓 `main...origin/main [ahead 34]`。
- Gensoulkyo #22 与 PhK-BattleServer #18 均为 `CLEAN` 且 checks 全绿，但都触及服务端/战斗服/协议/网络/安全边界，合并前仍需人工 diff 审阅并保留 protocol audit 证据。
- client-agent 已提交 `f5aa87e` 与 `8497655`，`client_smoke_test.gd` 和 `client_ui_smoke_test.gd` 通过；先前 parse 风险已被当前切片覆盖。但该分支仍相对远端 ahead 31，且未开 PR。
- 当前并行 agent 的输出速度仍高于合并/整理速度。下一阶段应先清 PR 队列、推送/开 PR 和旧 dirty worktree，再扩展新功能。

## PR 队列

| 仓库 | 状态 | 审计判断 |
| --- | --- | --- |
| SpellKard | #13/#15/#16/#18 `DIRTY`，#14/#17/#19 `BEHIND`，每个 PR 的 `client-static-audit` 与 `auto-merge` 已成功 | 不应继续扩新客户端 PR；client-agent 应新建 current-base 汇总 PR，或逐项 close/supersede 旧 PR。 |
| Gensoulkyo | #22 `CLEAN`，`server-contract-tests` 与 `auto-merge` 成功；本轮新增 `5562443`、`9c4e0c4`、`2d076a1` | 符合 Phase 3 业务服权威方向；涉及 settlement、service callback、Nakama RPC/WSS 边界，合并前需要人工 diff + protocol audit 证据。 |
| PhK-BattleServer | #18 `CLEAN`，`battle-server-checks` 与 `auto-merge` 成功；本轮新增 `a44a7e3`、`2b4ffbc` | 符合战斗服 replay/result audit 边界方向；涉及 replay/result/seed/session 边界，合并前需要人工 diff + protocol audit 证据。 |
| docs / PhK-Protocol | 无 open PR | docs 最新 #39 已合并，manager 会把 `next_agent_actions` 写入后续 agent prompt。 |

## 工作区风险

- `/root/gotouhou/docs`：本轮 audit-agent 新分支 `agent/audit-agent/status-risk-20260630-1225`，已 rebase 到最新 `origin/main`。
- `/root/gotouhou/SpellKard`：根仓 `main...origin/main [ahead 34]`，这是最大合并风险源。
- `/root/gotouhou/Gensoulkyo`：旧工作树仍有 4 个 dirty 文件，集中在 `cmd/gensoulkyo_nakama`，应由 nakama-server-agent 吸收、重建 PR 或明确废弃。
- client-agent worktree：干净，但 `agent/client-agent/persistent` 相对远端 ahead 31，且上一轮未推送/开 PR。
- nakama-server-agent worktree：干净；PR #22 已推送，远端 checks 重新成功。
- battle-server-agent worktree：干净；PR #18 已推送，远端 checks 重新成功。
- project-manager-agent worktree：干净；docs #40 已合并，`origin/main` 包含 repository state risk queue。

## 测试证据

- 最新全局回归摘要：2026-06-30T12:00:21Z，`ok=true`，`failed=0`，`ignored=0`。
- 全局回归包含：SpellKard `client_ui_smoke_test.gd`、`boss_pattern_catalog_check.gd`、cross-repo `protocol_audit_check.py`、Gensoulkyo `docker-compose config`、PhK-BattleServer `docker-compose config`。
- client-agent final：`python3 tools/ci_static_checks.py`、Godot `client_smoke_test.gd`、Godot `client_ui_smoke_test.gd` 通过；第二个 Boss intent 切片后也重跑静态检查和 `client_smoke_test.gd` 通过。
- nakama-server-agent final：`go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py` 通过。
- battle-server-agent final：`python3 tools/check_battle_server.py`、`docker-compose run --rm test`、`protocol_audit_check.py` 通过。
- 本轮 audit-agent 只改 docs 审计报告和 `.agents` 邮件正文，不改协议、网络、匹配、战斗服、鉴权或安全实现，因此未额外跑 protocol audit。

## Token 与旧 agent

- 12:36 manager dry-run：资源风险 high=1、medium=1。high 为 project-manager-agent，medium 为 legacy-agent-roster；audit/client/battle/nakama 当前运行样本为 low 或无 final token。
- 上一轮完成样本里 battle-server-agent、nakama-server-agent、client-agent token 偏高；后续报告只应摘要测试和 PR 状态，不复制长 diff/日志。
- 旧 agent 身份继续冻结：change-describer、gensoulkyo-lobby、phk-battle-server、plan-auditor、spellkard-bullet、spellkard-ui。只迁移已验证且仍有价值的工作到五个 managed agents。

## 下一步

- client-agent：推送/开 PR 或整理 `agent/client-agent/persistent` ahead 31，并把 7 个 SpellKard stale PR 收敛为一个 current-base PR 或 close/supersede 清单。
- nakama-server-agent：人工审阅 #22 的 service callback/full-version result gate diff，保留 protocol audit 证据后再合并；另处理根 Gensoulkyo 旧 dirty 4。
- battle-server-agent：人工审阅 #18 的 final snapshot/result owner/replay audit diff，保留 protocol audit 证据后再合并。
- project-manager-agent：继续把 dirty worktree、review gate、stale group 和 token 风险写入 `next_agent_actions`，避免只报数量。
- audit-agent：保持短中文审计，优先维护三小时邮件正文。
