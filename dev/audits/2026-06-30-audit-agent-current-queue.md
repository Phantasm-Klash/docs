# audit-agent 当前队列与风险审计

审计时间：2026-06-30T12:55:00Z

## 结论

- docs/dev 方向未变：主线仍是 Phase 3 服务器权威在线 MVP，围绕协议 v0.1、Nakama/Go 业务服、C++ Battle Server、PostgreSQL 持久化和正式 Godot UI 收敛。
- docs 根检出仍在 legacy/non-managed 分支 `agent/audit-agent/status-risk-20260630-1225`；本轮审计已改用 `origin/main` 新建 `agent/audit-agent/current-queue-20260630-1255`，避免把 legacy 根检出当基线。
- 上轮 docs PR #42 已关闭且未合并；三小时邮件不能继续把 #42 当作主线状态证据。
- 当前 open PR 只剩 SpellKard 8 个：#21 `CLEAN` 且 checks 成功，是当前唯一可审合的客户端汇总 PR；#13/#15/#16/#18 为 `DIRTY`，#14/#17/#19 为 `BEHIND`，应在 #21 合并或明确覆盖后关闭/标记 superseded。
- Gensoulkyo #22/#23 与 PhK-BattleServer #18/#19 已由对应 agent 审核、测试并合并；此前的 protocol/network/security review gate 已转为后续生产占位依赖风险，而非待合并 PR 风险。
- 旧 agent 身份继续冻结：`change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui`。只迁移已验证且仍有价值的工作到五个 managed agents。

## PR 队列

| 仓库 | 当前状态 | 审计判断 |
| --- | --- | --- |
| docs | open PR 0；#42 closed/unmerged | 当前 audit 报告必须从 `origin/main` 重建，不应继续堆在 #42 head。 |
| SpellKard | #21 `CLEAN`，`client-static-audit` 与 `auto-merge` 成功 | 符合客户端 Boss/replay/UI 合同收敛方向；合并前仍需人工读 diff，确认不把世界 Boss 击败时间、结算或奖励权威交给客户端。 |
| SpellKard | #13/#15/#16/#18 `DIRTY`，#14/#17/#19 `BEHIND` | 这些旧 UI/bullet PR 是当前最大队列负担；client-agent final 已声明 #21 取代它们，建议维护者审合 #21 后关闭旧 PR 组。 |
| Gensoulkyo | open PR 0 | #22/#23 已合并，service-origin callback gate 与 Nakama tag-build 验证已有测试证据；后续重点转向 PostgreSQL wiring、真实 envelope crypto 和 protobuf bindings。 |
| PhK-BattleServer | open PR 0 | #18/#19 已合并，result/replay audit 边界加强；后续重点转向真实 protobuf、Ed25519、X25519/HKDF、KCP 和 ChaCha20-Poly1305。 |
| PhK-Protocol | open PR 0 | 当前无队列；下一步仍是冻结 v0.1 并替换临时 manifest/descriptor 桥。 |

## Git 与 agent 风险

- `/root/gotouhou/SpellKard` 根仓仍是 `main...origin/main [ahead 34]`，是最高版本流风险；应由 client-agent 转成 current-base PR 或同步到 managed branch。
- `/root/gotouhou/Gensoulkyo` 根仓仍在 legacy 分支 `agent/gensoulkyo-lobby/20260629-0900` 且有 4 个 dirty 文件；nakama-server-agent final 表示有价值内容已通过 #23 迁入 main，但根检出不应被回滚或当基线。
- `/root/gotouhou/PhK-BattleServer` 根仓仍在 legacy 分支 `agent/phk-battle-server/20260629-0030`；已合并的 #18/#19 证据应以 main 和 managed worktree 为准。
- `/root/gotouhou/docs` 根检出出现未提交的 `ops/goal_agent_manager.py` 资源风险提示改动；本轮不触碰，等待 owning agent 提交或明确处理。
- 最新 manager dry-run 通过且 `started=0`：audit-agent、battle-server-agent、client-agent、project-manager-agent 为 running；nakama-server-agent 已 clean exit，dry-run 判定下一轮应补启；没有新的 failed agent 证据。
- 当前 dry-run 资源风险为 high=0、medium=3：client-agent 日志超过 1MB，nakama-server-agent 上轮 token 约 387,339，legacy-agent-roster 仍需冻结。下一轮应保持短切片、短报告、先提交再扩范围。

## 测试证据

- client-agent final：SpellKard #21 已跑 `python3 tools/ci_static_checks.py`、Godot `client_smoke_test.gd`、`boss_pattern_catalog_check.gd`、`client_ui_smoke_test.gd`、以及 `python3 /root/gotouhou/docs/ops/protocol_audit_check.py --root /root/gotouhou`。
- nakama-server-agent final：#22/#23 已跑 Nakama binding/tag-build 相关 Go tests、`go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`docker-compose --profile nakama-tag-build ...` 和 protocol audit。
- battle-server-agent final：#18/#19 已跑 `python3 tools/check_battle_server.py`、`docker-compose run --rm test` 和 protocol audit；host 缺 `cmake` 的直接 build 由 docker-compose 覆盖。
- 本轮 audit-agent 只新增 docs 审计报告并刷新 `.agents` 邮件正文，不改协议、网络、匹配、战斗服、鉴权或安全实现，因此最小检查为 py_compile、manager dry-run 和 `git diff --check`。

## 下一步

- client-agent：优先审合 #21，随后关闭/标记 #13/#14/#15/#16/#17/#18/#19 为 superseded；同时处理 SpellKard root `main` ahead 34。
- nakama-server-agent：从最新 main 继续 PostgreSQL audit sink/repository wiring、真实 X25519/AEAD/sign envelope 和完整 protobuf bindings；不要再从 root legacy checkout 取基线。
- battle-server-agent：从最新 main 继续 protobuf C++ 绑定、真实 Ed25519 result/ticket 验签、X25519/HKDF、KCP event loop 与 AEAD。
- project-manager-agent：继续把 dirty worktree、legacy checkout、PR supersede group、resource risk 写入 `next_agent_actions`，并处理 docs 根检出的 `goal_agent_manager.py` dirty 改动。
- audit-agent：保持短中文审计，优先维护三小时邮件正文；下一轮只在有新 PR/合并/回归证据时追加报告。
