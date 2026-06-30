# project-manager 调度快照 2026-06-30 18:07 UTC

## 结论

- 当前主线仍是 Phase 3：Nakama/Go 业务服与 C++ Battle Server 的服务器权威闭环；客户端只继续做本地展示、Replay、UI 和合同验证。
- docs #55 已合并，docs open PR 清零；SpellKard #27 仍是唯一 open PR，状态 CLEAN，两个检查通过，但 client-agent 已在同一分支继续产生 dirty=4，需先收敛当前切片再处理合并。
- 版本风险已从 docs dirty 转移到三个明确队列：battle-server-agent managed worktree `main` ahead=2 但无 open PR；nakama-server-agent managed worktree dirty=5；旧 Gensoulkyo checkout 仍有 4 个鉴权/安全相关 dirty 文件。
- 日志资源风险仍高：audit、battle、client、project-manager 需要只汇总检查、PR 状态和关键错误；不得继续粘贴长日志或大段 diff。

## Managed Agent 状态

| Agent | Worktree | dirty/ahead/behind | 最新日志 | Open PR | 强制下一步 |
| --- | --- | --- | --- | --- | --- |
| audit-agent | `/root/gotouhou/docs` `main...origin/main` | dirty=0 ahead=0 behind=0 | `audit-agent-20260630T174942Z.log` 727698 bytes, 18:03:54 UTC | 0 | 停止长日志；继续短审计，只记录结论、PR、检查和阻塞。 |
| battle-server-agent | managed PhK-BattleServer `main...origin/main` | dirty=0 ahead=2 behind=0 | `battle-server-agent-20260630T174725Z.log` 1421567 bytes, 18:02:34 UTC | 0 | 立即推送 ahead 提交并开 PR；PR body 必须列 `python3 tools/check_battle_server.py`、`docker-compose run --rm test`、protocol audit 结果或阻塞原因。 |
| client-agent | SpellKard `agent/client-agent/replay-boss-filter...origin/agent/client-agent/replay-boss-filter` | dirty=4 ahead=0 behind=0 | `client-agent-20260630T180229Z.log` 326762 bytes, 18:06:58 UTC | SpellKard #27 | 先收敛当前 dirty=4，运行 Godot/headless 与 protocol audit 后更新 #27 或写明阻塞；不要继续扩大 replay authority 变更。 |
| nakama-server-agent | managed Gensoulkyo `main...origin/main` | dirty=5 ahead=0 behind=0 | `nakama-server-agent-20260630T180052Z.log` 386039 bytes, 18:06:47 UTC | 0 | 先收敛 managed dirty=5，并裁决旧 `/root/gotouhou/Gensoulkyo` dirty=4；鉴权/安全相关改动必须跑 Go、docker-compose 和 protocol audit。 |
| project-manager-agent | docs persistent branch | dirty=1 ahead=0 behind=0 before commit | `project-manager-agent-20260630T180052Z.log` 300347 bytes, 18:06:59 UTC | 0 | 本轮提交此调度快照，跑 ops 最小检查，再做正常 manager 复采样。 |

## PR 与回归

- docs：open PR=0；#55 `Add 17:54 audit status snapshot` 已合并。
- SpellKard：#27 `Expose boss practice replay filter`，CLEAN，`auto-merge` 和 `client-static-audit` 均通过；但同分支已有新 dirty=4，本轮只做管理记录，未合并。
- Gensoulkyo / PhK-BattleServer / PhK-Protocol：open PR=0。
- 最新回归采样：`/root/gotouhou/.agents/checks/latest-regression.json` generated_at=2026-06-30T18:00:44Z，ok=true，failed_count=0，ignored_count=0。

## 下一轮调度优先级

1. client-agent：先收敛 SpellKard dirty=4，更新 #27 或写明阻塞，不继续扩大同一分支。
2. nakama-server-agent：先收敛 managed dirty=5，再给旧 Gensoulkyo dirty=4 做保留/迁移/废弃裁决；安全相关改动必须 protocol audit。
3. battle-server-agent：把 ahead=2 变成 PR，停止 only-local 堆积。
4. audit-agent/project-manager-agent：保持短报告；业务 PR 合并后立即跑正常 manager 复采样。
5. 所有 agent：资源风险未解除前，final 和日志只写短摘要、检查名、PR URL、关键错误。
