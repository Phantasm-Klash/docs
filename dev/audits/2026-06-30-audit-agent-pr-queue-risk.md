# audit-agent PR 队列与 agent 风险审计

审计时间：2026-06-30 11:49 UTC

## 结论

- docs/dev 方向未变：当前仍应围绕 Phase 3 服务器权威在线 MVP 收敛，优先冻结协议 v0.1、Nakama/Go 业务服边界、C++ Battle Server 结算边界、PostgreSQL 持久化与正式 Godot UI。
- docs #32 与 docs #33 已合并；docs 当前无 open PR。本轮 audit-agent 已从最新 `origin/main` 新建 `agent/audit-agent/pr-queue-risk-20260630-1150`，避免继续在已删除的 #32 head 分支上堆提交。
- 当前 open PR 为 9 个：Gensoulkyo #22 与 PhK-BattleServer #18 为 `CLEAN` 且 checks 通过；SpellKard #13-#19 共 7 个仍为 stale group，其中 4 个 `DIRTY`、3 个 `BEHIND`。
- #22/#18 虽然 merge-ready，但都触及服务端、战斗服、协议/网络/安全边界；project-manager #33 已把它们标成 review gate。下一步应人工读 diff、保留 protocol audit 证据后再合并，不能把 checks 全绿视为自动安全。
- 最高版本流风险仍是 SpellKard：根仓 `main...origin/main [ahead 34]`，同时 7 个旧 PR 未收敛。client-agent 应先 fresh current-base PR 或明确 supersede/close 决策，再扩新 UI/Boss 功能。
- Gensoulkyo 根仓仍有旧 dirty 4：`cmd/gensoulkyo_nakama/README.md`、`module.go`、`module_source_test.go` 和新增 `module_nakama_test.go`。这些改动收紧 Nakama service-origin 回调上下文，属于安全边界，应由 nakama-server-agent 吸收、重建为 PR 或明确废弃，并跑 protocol audit。
- 旧 agent 身份应继续冻结：`change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui`。只迁移已验证且仍有价值的工作到五个 managed agents。

## PR 队列

| 仓库 | PR | 状态 | 审计判断 |
| --- | --- | --- | --- |
| docs | #34 `Surface next agent action queue` | `CLEAN`，2 checks 通过 | 方向正确：在 PR 队列和资源风险之上生成结构化 `next_agent_actions`，并渲染到三小时邮件，能把 stale PR、review gate 与 token 风险转成可执行队列。只改 `ops/goal_agent_manager.py` 与 `ops/hourly_progress_mail.py`，不改协议/网络/安全实现；合并时注意与 #35 的 docs 报告顺序。 |
| docs | #35 `Audit PR queue risk gates` | `CLEAN`，2 checks 通过 | 本审计报告 PR，补充 #22/#18 review gate、SpellKard stale group、Gensoulkyo dirty 4、token 风险和旧 agent 清退建议。 |
| Gensoulkyo | #22 `Tighten business settlement and service callback contracts` | `CLEAN`，2 checks 通过 | 符合 Phase 3 业务服权威方向；涉及 service callback、settlement/result projection、Nakama RPC/WSS 边界，合并前需要人工 diff 审阅与 protocol audit 证据。 |
| PhK-BattleServer | #18 `Bind boss defeated tick projection` | `CLEAN`，2 checks 通过 | 符合 C++ Battle Server 结算/投影验真方向；分支还包含 decoded session boundary，合并前需要人工 diff 审阅与 protocol audit 证据。 |
| SpellKard | #13/#15/#16/#18 | `DIRTY` | 不应继续堆新功能扩大冲突面；建议重建一个 current-base PR 或逐项记录 supersede。 |
| SpellKard | #14/#17/#19 | `BEHIND` | 更新分支并重跑 checks 后再审；若已被 main 等价覆盖，应由 client-agent 明确 close/supersede。 |

## Agent 与资源风险

- 当前 5 个 managed agents 均为 running：client-agent、battle-server-agent、nakama-server-agent、audit-agent、project-manager-agent；无 failed agent。
- 11:46 manager summary 的上一轮完成样本显示资源风险 high：nakama-server-agent 约 1,178,498 tokens、battle-server-agent 约 705,504 tokens、project-manager-agent 约 582,452 tokens。后续必须拆更短 PR-ready 切片。
- 11:46 manager summary 的上一轮完成样本显示资源风险 medium：audit-agent 约 476,577 tokens、client-agent 约 317,186 tokens、legacy-agent-roster。client-agent 虽为 medium，但日志体积较大且 SpellKard PR 堆积明显。
- 11:51 `goal_agent_manager.py --dry-run --no-start` 对当前运行中 agent 只看到 `running_without_final_token_sample`，因此当前采样的 high=0、medium=1 不能说明 token 风险已经消失，只说明这一轮还没有 final token 读数。
- 当前没有新五 agent 停滞证据；风险来自“产出速度 > 合并/清退速度”，不是 agent 未运行。

## 测试证据

- 最新全局回归摘要：2026-06-30T09:00:24Z，`ok=true`、`failed=0`、`ignored=0`。
- Gensoulkyo #22 GitHub checks：`server-contract-tests` 与 `auto-merge` 通过；PR body 声明本地跑过 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py`。
- PhK-BattleServer #18 GitHub checks：`battle-server-checks` 与 `auto-merge` 通过；PR body 声明本地跑过 `python3 tools/check_battle_server.py`、`docker-compose run --rm test`、`protocol_audit_check.py`。
- 本轮 audit-agent 只新增 docs 审计报告并更新 `.agents` 邮件正文，不改协议、网络、匹配、战斗服、鉴权或安全实现。

## 下一步

- client-agent：先处理 SpellKard stale group 和 root main ahead 34，形成一个 fresh current-base PR 或明确 close/supersede 清单。
- nakama-server-agent：审阅并合并 #22 后同步工作树；处理旧 dirty 4；继续 Nakama tag-build CI、PostgreSQL audit sink wiring 与 service-origin callback 持久化。
- battle-server-agent：审阅并合并 #18 后，从 protobuf C++ decode、真实 Ed25519 ticket/result 验签、X25519/KCP/AEAD 继续推进。
- project-manager-agent：继续把 review gate、stale group、dirty worktree 和 token 风险写成可执行队列，避免邮件只报数量。
- audit-agent：继续短中文审计 PR/dirty work/测试证据/旧 agent 清退/token 风险，并优先维护三小时邮件正文。
