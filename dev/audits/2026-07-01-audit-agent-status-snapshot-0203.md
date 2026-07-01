检查命令与结果：`py_compile`、`check_goal_agent_manager.py`、`goal_agent_manager.py --dry-run --root /root/gotouhou` PASS；五仓 open PR=0；最新回归 ok。
PR/branch 状态：docs/main clean；#63/#64/#53/#69 均已合并且必需 checks success；battle-server-agent managed worktree upstream-gone；nakama managed worktree dirty=2。
失败命令：`gh pr list --repo lychees/*` 仓库 owner 错误，已用 Phantasm-Klash 重查成功。
首个关键错误：Gensoulkyo root 仍在 legacy `agent/gensoulkyo-lobby/20260629-0900` 且 dirty=4，不可作为基线。
下一步动作：nakama-server-agent 先收敛 managed dirty=2 与 legacy dirty=4；battle-server-agent 切回已合并 main；所有中高资源风险 agent 继续压缩输出。
