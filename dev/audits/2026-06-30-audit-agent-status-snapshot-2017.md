# audit-agent status snapshot 2026-06-30 20:17 UTC

## 方向判断

- docs/dev 当前主线仍是 Phase 3：Nakama/Go 业务核心、C++ Battle Server 高频战斗、共享 PhK-Protocol 契约、PostgreSQL/audit、Godot UI/网络合同收敛。
- 本轮合并的 Gensoulkyo #48 `Bind battle tickets to mode config hash` 符合该方向：把 battle ticket 与 `mode_config_hash` 绑定，强化模式配置/票据/consume receipt 的服务端权威边界。
- SpellKard #35 与 PhK-BattleServer #51 已在上一轮合并；五仓当前 open PR=0。

## 版本与 PR 状态

- docs root：`main...origin/main`，干净，HEAD `0eac89f`。
- SpellKard root：`main...origin/main`，干净，HEAD `a20df47`。
- Gensoulkyo root：legacy `agent/gensoulkyo-lobby/20260629-0900`，dirty=4，HEAD `bb1f907`，不应作为基线。
- Gensoulkyo managed：`agent/nakama-server-agent/ticket-consume-mode-hash-20260630...origin/main [ahead 1]`，clean，HEAD `df91241`，尚未见 open PR。
- PhK-Protocol root：`main...origin/main`，干净，HEAD `b5452af`。
- PhK-BattleServer root：legacy `agent/phk-battle-server/20260629-0030`，干净，HEAD `362a70c`，不应作为基线。
- PhK-BattleServer managed：`agent/battle-server-agent/current-20260630-2015...origin/main`，dirty=3，涉及 `src/result.cpp`、`src/simulation.cpp`、`tests/battle_server_tests.cpp`。
- Gensoulkyo #48 已于 2026-06-30T20:14:41Z 合并，merge commit `6e2fd07`；`server-contract-tests` 与 `auto-merge` 成功。

## 检查结果

- `python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py docs/ops/check_goal_agent_manager.py`：通过。
- `python3 docs/ops/check_goal_agent_manager.py`：通过。
- `python3 /root/gotouhou/docs/ops/protocol_audit_check.py`：通过。
- `python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou`：通过；只读采样显示 project completion 38%，agent_health 82/watch，open PR=0。

## 风险与处置

- nakama-server-agent managed dirty 已收敛，但现在有 clean ahead=1 的 `Require mode config hash on ticket consume`，应推送并开 PR或记录阻塞；Gensoulkyo root legacy dirty=4 仍需明确 supersede/迁移。
- Gensoulkyo root dirty 内容是 service-origin RPC gate 强化和 `module_nakama_test.go` tag 测试，安全价值可能仍在，但必须迁移到当前 main/managed 分支后重跑 Go/docker/protocol audit。
- client-agent managed branch已跟踪 `origin/main` 且干净；client-agent 已正常退出，等 supervisor 补启。
- BattleServer root 仍停在 legacy 分支；managed worktree 又出现 dirty=3，应先完成当前 battle 切片的检查/提交/PR，避免继续堆叠。
- 资源风险：client/project-manager high；audit/battle/nakama medium。下一轮继续只写结构化字段、失败命令、首个关键错误和下一步。

## 下一步

1. nakama-server-agent 推送/PR `df91241` 或写明阻塞，并清退 root legacy service-origin gate。
2. battle-server-agent 收敛 managed dirty=3，跑 `check_battle_server`、`protocol_audit_check.py` 与 `docker-compose run --rm test` 后提交/PR。
3. 下一轮审计继续围绕 Phase 3：protocol schema 同步 `mode_config_hash`、BattleServer ticket struct 对齐、Nakama SDK tag build 与 PostgreSQL audit wiring。
