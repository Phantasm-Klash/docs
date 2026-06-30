# audit-agent resource status 2026-06-30 17:25Z

## 方向判断

- docs/dev 主线仍是 Phase 3：Nakama/Go 业务服、C++ Battle Server、共享协议冻结和多仓 CI 收敛。
- 最近提交方向基本匹配：SpellKard 继续 Boss/replay/UI authority surface；Gensoulkyo 继续 Nakama callback/envelope guard；PhK-BattleServer 继续 packet/session/reconnect guard；PhK-Protocol 已补 snapshot/event/golden replay fixture。
- Steam closed layer 仍应保持 pending，不应提前扩展。

## PR 与分支状态

- docs: `main` 干净基线为 `11a3f32`，本审计切片仅修改 ops 报告渲染和新增本文件。
- SpellKard: root `main` behind origin 4 commits；唯一 open PR 为 #25 `DIRTY`，需 client-agent rebase/resolve 或 supersede。
- Gensoulkyo: root 在 legacy branch `agent/gensoulkyo-lobby/20260629-0900`，dirty 4；managed worktree 另有 `runtime/httpapi/handler.go` dirty 1，nakama-server-agent 应先收敛版本流程。
- PhK-BattleServer: root 仍在 legacy branch `agent/phk-battle-server/20260629-0030`，不应作为新基线；managed worktree 在 main 干净。
- PhK-Protocol: main 干净，无 open PR。

## 资源风险

- client-agent: high；日志约 3.58MB；原因 `running_without_final_token_sample` 和 `log_bytes>=3000000`；下一步必须压缩输出，只汇总检查、PR 和关键错误。
- project-manager-agent: medium；上一轮 token 约 412k；下一步只做短调度切片并先提交/推送已验证成果。
- old roster: `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 继续冻结，只迁移有价值工作到五个 managed agents。

## 下一步

- client-agent: 先处理 SpellKard #25 冲突和 root main behind，不扩展新 UI。
- nakama-server-agent: 先处理 legacy dirty 4 与 managed dirty 1，保留有价值改动后提交/PR 或写明废弃。
- battle-server-agent: 迁移或清退 legacy root branch，不把旧分支当基线。
- audit-agent/project-manager-agent: 三小时邮件优先使用结构化字段，避免复制长日志尾部。
