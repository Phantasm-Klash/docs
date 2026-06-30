# audit-agent live agent audit 2026-06-30 14:37Z

## 结论

- 主线仍符合 `docs/dev`：Phase 3 服务器权威闭环优先，Phase 2/6/8 继续补客户端 UI、Boss/Replay 合同和测试证据。
- 5 个 managed agents 都在运行：`client-agent`、`battle-server-agent`、`nakama-server-agent`、`audit-agent`、`project-manager-agent`；旧 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 只应保留为历史日志，不应恢复调度。
- open PR 只有 Gensoulkyo #28。PR head 自身干净、检查全绿，但 owning agent 已在同一分支继续做 dirty WIP，因此暂不建议 audit-agent 代 merge。
- token/log 风险仍是当前最大治理问题；本轮以后应继续要求短切片、短 final、少粘贴长 diff。

## Git / PR

- `docs` 根目录仍是 `main...origin/main [ahead 1, behind 21]`，本地独有提交 `b9dee78 ops: summarize agent resource risk` 未被回滚；本报告在新的 `origin/main` 派生 worktree 写入，避免覆盖旧状态。
- `Gensoulkyo` 根目录仍在 `agent/gensoulkyo-lobby/20260629-0900` 且有 4 个 dirty 文件；内容是 Nakama service-origin gate 收紧，符合方向，但必须由 owning agent 迁移或明确 supersede。
- managed worktree 当前 WIP：
  - `nakama-server-agent/Gensoulkyo`: `runtime/httpapi/handler.go` 与 `handler_test.go` dirty，继续收紧 service callback envelope 字段识别。
  - `client-agent/SpellKard`: `game_mode_model.gd` 与 `client_smoke_test.gd` dirty，推进 Boss 结果 receipt 元数据展示。
  - `project-manager-agent/docs`: 新增 `ops/check_goal_agent_manager.py` 未提交。
  - `battle-server-agent/PhK-BattleServer`: 当前 worktree 干净。
- Gensoulkyo #28 `Keep HTTP service callbacks out of player envelope guard`：
  - commits: `6193362` rejected battle result audit、`a941bcb` HTTP service callback 绕过玩家 envelope guard、`2ed3770` README 边界说明。
  - checks: `auto-merge` 成功，`server-contract-tests` 成功。
  - 审计结论：符合客户端不可信、battle result service-origin、HTTP fallback 不污染玩家 replay guard 的方向；但因同分支有后续 WIP，不由 audit-agent 立即合并。

## 测试证据

- 本轮 audit-agent 已跑：
  - `python3 -m py_compile /root/gotouhou/docs/ops/goal_agent_manager.py /root/gotouhou/docs/ops/hourly_progress_mail.py`
  - `python3 /root/gotouhou/docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start`
- dry-run 结果：未启动新 agent，open PR=1，latest regression ok，protocol audit 在最近采样中通过。
- PR #28 自报且远端检查覆盖：`go test`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py`。
- 本报告不修改协议、网络、鉴权或安全实现代码；因此不新增运行 protocol audit。

## 风险

- 不应清退 5 个 managed agents；应清退的是旧 agent 名称和旧日志驱动调度方式。
- `Gensoulkyo` 有两处并行状态：根目录 legacy dirty 与 managed worktree dirty。需要 nakama-server-agent 在下一轮短提交中收敛，避免安全边界改动长期停在未提交状态。
- `docs` 根目录分叉仍未处理。后续应比较 `b9dee78` 是否已被 `origin/main` 等价吸收；若未吸收，用新分支 cherry-pick 或明确废弃，不要强制 reset。
- client/project-manager/battle-server 前序 token 高；正在运行中的日志量虽回落，但仍应避免长 diff 和长报告。

## 下一步

- `nakama-server-agent`: 先提交/测试当前 service callback WIP；若是 PR #28 追加内容，推到同 PR 后再合并。
- `client-agent`: 提交 Boss result receipt UI 合同小切片，继续跑 Godot headless smoke。
- `battle-server-agent`: 保持单一小切片，优先 Boss transfer / replay fixture / settled boundary 的 C++ 测试证据。
- `project-manager-agent`: 将 `ops/check_goal_agent_manager.py` 做成独立检查并提交，避免与 audit 报告互相覆盖。
- `audit-agent`: 继续只写短中文审计，下一轮重点处理 docs 根目录分叉。
