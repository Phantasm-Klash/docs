# audit-agent 阶段审计报告

审计时间：2026-06-30 09:45 UTC

## 总体判断

- docs/dev 主线未变：项目仍处于 Phase 3，核心是 PhK-Protocol 共享协议、Nakama/Go 业务服、C++ Battle Server 与 SpellKard 客户端在服务器权威在线 MVP 下收敛。
- 本轮服务端 agent 又产出新 PR：Gensoulkyo #19 与 PhK-BattleServer #16 均为 open、mergeable，且 GitHub required checks 通过；方向分别对应 HTTP battle callback fallback 与 Boss result projection 字段验证，符合 Phase 3/8 的权威边界。
- 当前 open PR 总数为 9：SpellKard #13-#19 共 7 个旧 PR，Gensoulkyo #19，PhK-BattleServer #16。docs 与 PhK-Protocol open PR 为 0。
- 整体完成度仍按约 38% 估算。当前没有 agent 停滞证据，五个新 agent 均处于 running 或刚完成后被 manager 续启；主要风险是客户端旧 PR 队列、SpellKard 本地 main ahead 34、Gensoulkyo 根工作树旧 lobby dirty 4，以及单轮 token 消耗持续偏高。
- 旧 agent 身份 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 应继续冻结，只保留历史记录，不应重新启动。

## 仓库状态

- `docs`：当前基线 `main...origin/main` 干净，最新为 `1d099b6 Merge pull request #24`；本轮审计使用 `agent/audit-agent/20260630-0945b` 分支更新报告。
- `SpellKard`：根工作树 `main...origin/main [ahead 34]` 且干净，最新本地提交 `ff181cd Guard spellbook preview source authority`。该 ahead 堆叠与 7 个旧 open PR 并存，是最高版本流风险。
- `Gensoulkyo`：根工作树仍停在旧 `agent/gensoulkyo-lobby/20260629-0900`，有 4 个未提交 Nakama callback gate 改动；新 persistent worktree 已开 #19。旧 dirty work 不应由 audit-agent 回滚，应由 nakama-server-agent 或 manager 基于最新 main 决定重建、吸收或废弃。
- `PhK-BattleServer`：根工作树仍在旧 `agent/phk-battle-server/20260629-0030` 且干净；新 persistent worktree 已开 #16。旧根分支可保留历史，但不应再作为活跃 agent 入口。
- `PhK-Protocol`：`main...origin/main` 干净，最新仍为 `b5452af Export golden replay summary fixture (#6)`；无 open PR。风险仍是临时 manifest/JSON bridge 尚未替换为真实 protobuf Go/C++/Godot 生成物。

## Agent 采样

- `client-agent`：运行中，正在采样 SpellKard #13-#19 队列；上一轮已记录 Godot/static 检查通过。方向仍是 UI/Boss/Replay/服务端投射，但需要优先把旧 PR 队列重建为一个 fresh PR 或写清 supersede/关闭依据，避免继续堆叠 ahead。
- `battle-server-agent`：运行中；最近完成并开 PR #16 `Validate boss result projection fields`。GitHub `battle-server-checks` 与 `auto-merge` 通过，符合 Boss result projection、defeat/clear/disposition 权威验证方向。
- `nakama-server-agent`：运行中；最近完成并开 PR #19 `Add HTTP battle callback fallback routes`，提交含 battle ticket consume、battle server offline fallback、文档更新。记录的验证为 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`protocol_audit_check.py`、`docker-compose --profile test run --rm test` 通过；GitHub `server-contract-tests` 与 `auto-merge` 通过。
- `audit-agent`：本轮刷新中文审计与邮件正文，更新 open PR、dirty work、测试证据、旧 agent 清退与 token 风险。
- `project-manager-agent`：运行中；上一轮合并 docs #24 前的项目经理报告仍有效，但其中“服务端 PR 队列已清空”的事实已被 #19/#16 更新，应在下一轮管理报告中刷新。

## PR 与版本风险

- 当前 open PR：SpellKard #13-#19、Gensoulkyo #19、PhK-BattleServer #16，共 9 个。
- SpellKard #13/#15/#16/#18 为 conflict/dirty，#14/#17/#19 为 mergeable/behind；历史 CI 都通过，但不能证明已被当前 `main` 或 client persistent 覆盖。应优先由 client-agent 重建一个基于最新 main 的综合 PR，或逐个关闭并注明被哪些本地提交替代。
- Gensoulkyo #19 与 PhK-BattleServer #16 均可进入 review/merge 流程；合并前仍应阅读 diff，确认没有把高频 tick、客户端提交结算或奖励写入业务服，也没有绕过战斗服 result projection 验证。
- Gensoulkyo 根工作树 dirty 4 属于旧 `gensoulkyo-lobby` 遗留，方向可能与 #19/#18 部分重叠；建议 manager 让 nakama-server-agent 在最新 main 上做 cherry/supersede 判断，不要直接复用旧分支。
- Token 风险偏高：近期 project-manager 约 105 万 tokens、nakama-server 约 56 万、audit 约 46 万；应继续压缩报告正文，只保留结论、PR 状态、测试证据和下一步。

## 测试证据

- 最新全局回归摘要：2026-06-30T09:00:24Z，`ok=true`、`failed=0`、`ignored=0`。
- 全局摘要包含 SpellKard Godot headless UI/Boss 检查、跨仓 `protocol_audit_check.py`、Gensoulkyo 与 PhK-BattleServer `docker-compose config`，docker 与 docker-compose 均可用。
- Gensoulkyo #19 记录了 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`python3 /root/gotouhou/docs/ops/protocol_audit_check.py`、`docker-compose --profile test run --rm test` 通过，且 GitHub checks 通过。
- PhK-BattleServer #16 GitHub `battle-server-checks` 与 `auto-merge` 通过；因涉及战斗服结果字段，合并前仍应保持 protocol audit/dockers checks 证据。
- 本轮 audit-agent 仅更新报告和邮件正文，不改协议、网络、匹配、战斗服、鉴权或安全代码；按 persona 最小检查运行 docs/ops py_compile 与 goal manager dry-run。

## 下一步

- project-manager-agent：更新 PR 队列事实，优先 review/merge 或协调 Gensoulkyo #19、PhK-BattleServer #16；继续压制 SpellKard 队列膨胀。
- client-agent：暂停扩展无关 UI/Boss 新功能，先把 SpellKard #13-#19 转为一个最新 main 基线 PR，或写出可审计的 supersede 关闭清单。
- nakama-server-agent：合并 #19 后从最新 main 继续 durable PostgreSQL repositories 或 production S2S auth/crypto；单独处理旧 lobby dirty 4。
- battle-server-agent：合并 #16 后继续 Boss failure/defeat-required result verification、mode-config card-state 初始化、真实 crypto/KCP/protobuf 依赖替换；协议/战斗服变更继续跑 `docker-compose` 和 protocol audit。
- audit-agent：继续短中文审计 PR、dirty work、测试证据、旧 agent 清退与 token 风险；三小时邮件正文以本报告的结论和风险为主。
