# audit-agent 阶段审计报告

审计时间：2026-06-30 11:16 UTC

## 总体判断

- docs/dev 主线未变：整体仍按约 38% 估算，当前主线是 Phase 3 服务器权威在线 MVP 与服务拆分收敛；Phase 2/6/8 的客户端、UI、Boss 模式切片并行补齐。
- 服务端方向继续符合路线：Gensoulkyo #22 聚焦 settlement business event alias 与 service callback envelope 边界，PhK-BattleServer #18 聚焦 Boss result/replay 投影验真和已结算 match 冻结，均对齐 Nakama 业务服 + C++ Battle Server 的服务器权威拆分。
- docs 管理闭环已有推进：project-manager-agent 的 docs #30 已合并到 `origin/main`，manager summary 现在能单列 stale PR group 与 merge-ready PR；audit-agent 继续用 docs #28 承载三小时邮件优先审计正文。
- 最高版本流风险仍是 SpellKard：open PR #13-#19 共 7 个，4 个 `DIRTY`、3 个 `BEHIND`；根仓 `main...origin/main [ahead 34]`，client-agent persistent 分支 `ahead 23`。应先清队列或开 fresh current-base PR，暂停继续扩 UI/Boss 功能面。
- Gensoulkyo 根仓仍在旧 `agent/gensoulkyo-lobby/20260629-0900` 且有 4 个未提交变更信号：`cmd/gensoulkyo_nakama/README.md`、`module.go`、`module_source_test.go` 和新增 `module_nakama_test.go`。audit-agent 不回滚，建议 nakama-server-agent 吸收、重建或明确废弃。
- 旧 agent 身份 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 应继续冻结，只把已验证且仍有价值的提交迁移进五个 managed agents。

## 仓库状态

- `docs`：当前分支 `agent/audit-agent/resource-risk-20260630-1022` 与远端对齐且工作树干净；PR #28 `Summarize agent resource risk` 为 `CLEAN`，checks 2/0/0。
- `SpellKard`：根仓 `main...origin/main [ahead 34]` 且干净；client-agent worktree `agent/client-agent/persistent...origin/agent/client-agent/persistent [ahead 23]`。
- `Gensoulkyo`：根仓在旧 `agent/gensoulkyo-lobby/20260629-0900`，dirty 4；nakama-server-agent worktree `agent/nakama-business-event-settlement-alias` 与远端对齐，PR #22 为 `CLEAN`。
- `PhK-BattleServer`：根仓在旧 `agent/phk-battle-server/20260629-0030` 且干净；battle-server-agent worktree `agent/battle-server-agent/persistent` 与远端对齐，PR #18 为 `CLEAN`。
- `PhK-Protocol`：`main...origin/main` 干净，open PR 为 0；仍需把临时 manifest/JSON bridge 收敛为真实 protobuf Go/C++/Godot 生成物。

## PR 与版本风险

- 当前 open PR 数：10；needs_action=7，merge_ready=3。
- merge-ready：docs #28、Gensoulkyo #22、PhK-BattleServer #18 均为 `CLEAN` 且 checks 通过。#22 已推送 head 为 7 个提交，本轮抽审覆盖 settlement alias、service callback envelope guard 与 forbidden battle result projection，未见偏离 docs/dev 服务器权威方向的明显问题；#22/#18 涉及安全/协议/战斗边界，合并前仍应人工审阅 diff 并保留 protocol audit 证据。
- SpellKard #13/#15/#16/#18：`DIRTY`，需要冲突解决或由 current-base fresh PR 明确 supersede。
- SpellKard #14/#17/#19：`BEHIND`，需要更新分支、重跑 checks、评审，或由 fresh PR 明确 supersede。
- 本地 ahead 风险比 PR 风险更大：SpellKard 根仓 ahead 34 与 client-agent worktree ahead 23 会让后续 PR 继续扩张冲突面。

## Agent 采样

- `client-agent`：运行中；最新 final 完成 Boss playfield projection 与绘制层，Godot/static 检查通过。风险是 ahead 23 与 7 个旧 PR 积压。
- `battle-server-agent`：运行中；最新 final 完成 Boss start readiness result projection 与已结算 match 冻结，`tools/check_battle_server.py`、`docker-compose run --rm test`、`protocol_audit_check.py` 通过。
- `nakama-server-agent`：运行中；最新 final 完成 service-origin RPC/HTTP fallback 拒绝嵌套或直接携带 business envelope 的 callback payload，Go tests、docker-compose test、protocol audit 通过。本轮采样时该 worktree 又有 `runtime/httpapi/handler_test.go` 与 `runtime/nakamaapi/handler_test.go` 两个本地测试文件 dirty，若继续推送到 #22，需按最新 head 重采样。
- `project-manager-agent`：运行中；最新 final 完成 `merge_ready_items`，docs #30 已合并。
- `audit-agent`：本轮刷新阶段审计报告、邮件优先正文和 final 日志，重点校正 open PR=10、merge-ready=3、SpellKard ahead 23、Gensoulkyo dirty 4。

## 测试证据

- 最新全局回归摘要：2026-06-30T09:00:24Z，`ok=true`、`failed=0`、`ignored=0`。
- 全局摘要包含 SpellKard Godot headless UI/Boss 检查、跨仓 `protocol_audit_check.py`、Gensoulkyo 与 PhK-BattleServer `docker-compose config`；docker 与 `docker-compose` 均可用。
- 本轮 audit-agent 只改 docs 审计报告和 `.agents` 邮件正文，不改协议、网络、匹配、战斗服、鉴权或安全代码；按人格文档运行 ops 最小检查即可。

## Token 与停滞风险

- token 消耗风险偏高：nakama-server-agent 约 1.30M、battle-server-agent 约 873k、client-agent 约 687k、audit-agent 约 484k、project-manager-agent 约 389k。后续每轮应更短，先提交/推 PR，再扩下一切片。
- 停滞风险主要来自三类队列：SpellKard stale PR group、Gensoulkyo 旧 dirty worktree、ready PR 合并速度慢于 agent 产出速度。
- 新五 agent 当前均有进展证据；需要清退的是旧 roster 与旧 worktree，不是新 goal agents。
- 第二轮 PR 抽审结论：Gensoulkyo #22 可继续作为 merge-ready 候选，但 active agent 已有本地 dirty 测试改动，若继续推送则审计/测试证据必须随最新 head 重采样。

## 下一步

- client-agent：优先处理 SpellKard #13-#19 和 ahead 23，开一个 fresh current-base PR 或逐项记录 supersede/close 决策。
- nakama-server-agent：合并 #22 后同步工作树，优先 Nakama tag-build CI、service-origin result/ticket 回调持久化或 PostgreSQL repository wiring。
- battle-server-agent：合并 #18 后再推进 protobuf C++ 绑定、真实 Ed25519 ticket/result 验签、X25519/KCP/AEAD。
- project-manager-agent：继续把 stale group 和 merge-ready 输出变成可执行清退表，避免三小时邮件只报告数量。
- audit-agent：保持短中文审计，继续追踪 PR/dirty work/测试证据/旧 agent 清退/token 风险。
