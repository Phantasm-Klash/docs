# audit-agent 阶段审计报告

审计时间：2026-06-30 08:12 UTC

## 总体判断

- docs/dev 当前主线仍是 Phase 3：Nakama/Go 业务服、C++ BattleServer、PhK-Protocol 共享协议和 SpellKard 客户端投射收敛，服务器权威、协议冻结、持久化和生产级传输仍是最高优先级。
- 当前管理面已从旧 scope roster 收敛到五个 `/goal` agent：client-agent、battle-server-agent、nakama-server-agent、audit-agent、project-manager-agent。旧 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 只应归档，不应重新启动。
- 最近阶段提交总体符合 docs/dev：client-agent 推进 Boss formation 和卡牌让渡本地预检；battle-server-agent 推进 Boss 权威 HP/伤害与结果投射；nakama-server-agent 推进房间审计和 matchmaking cancel 合同；PhK-Protocol 保持 golden replay/snapshot/mode-action fixture 稳定。
- 新增 project-manager-agent 的方向合理：它承担跨 agent 计划收敛和 supervisor 节奏拆分，能降低 audit-agent 同时做审计和调度的职责混杂。但当前 docs 工作树已有未提交 ops 改动，必须由 project-manager-agent 完成测试、提交和 PR/说明，audit-agent 本轮不接管。
- GitHub PR 实时查询被本机 `socks5h` 代理连接失败阻塞，不能把 open PR 视为 0；邮件和 manager 报告必须标注这是采集失败，不是无 PR。

## 仓库状态

- `docs`：`main...origin/main [ahead 2]`，工作区存在未提交 `ops/README.md`、`ops/goal_agent_manager.py`，以及未跟踪 supervisor runner/systemd unit。改动方向是 project-manager-agent/15 分钟 supervisor；audit-agent 本轮只提交本审计报告，避免混入他人改动。
- `PhK-Protocol`：`main...origin/main`，工作区干净。最新本地提交 `b5452af Export golden replay summary fixture (#6)`，符合 v0.1 合同冻结方向。
- `SpellKard`：`main...origin/main [ahead 34]`，工作区干净。本地 main 长期领先远端是主要版本流风险，应尽快推送、拆 PR 或明确保留本地队列的原因。
- `Gensoulkyo`：`agent/gensoulkyo-lobby/20260629-0900...origin/agent/gensoulkyo-lobby/20260629-0900`，存在 4 个未提交 Nakama 绑定相关改动。改动方向属于 Phase 3 安全/传输边界，必须由 nakama-server-agent 完成测试、提交和 PR/说明，audit-agent 不接管。
- `PhK-BattleServer`：`agent/phk-battle-server/20260629-0030...origin/agent/phk-battle-server/20260629-0030`，工作区干净。近期提交集中在加密会话、reconnect、decoded packet 和 replay/hash 边界。

## Agent 采样

- client-agent worktree：`agent/client-agent/persistent...origin/agent/client-agent/persistent [ahead 4]`，工作区干净，最新提交 `32c61f1 Guard boss transfer requests locally`。本轮验证记录包含 `python3 tools/ci_static_checks.py` 与三个 Godot headless smoke。
- battle-server-agent worktree：`agent/battle-server-agent/persistent...origin/agent/battle-server-agent/persistent [ahead 4]`，工作区干净，最新提交 `05cf7fe Project boss state into battle results`。本轮验证记录包含 `python3 tools/check_battle_server.py`、`docker-compose run --rm test` 和 protocol audit。
- nakama-server-agent worktree：`agent/nakama-server-agent/persistent...origin/agent/nakama-server-agent/persistent`，工作区干净，最新提交 `0887477 Publish matchmaking cancel room rule`，已推送到远端同名分支。本轮验证记录包含 Go tests、`docker-compose --profile test run --rm test` 和 protocol audit。
- project-manager-agent：当前 systemd transient unit 运行中，正在审阅并准备提交 docs/ops 的 project-manager/supervisor 改动；其最终日志尚未生成。
- audit-agent：本轮负责中文审计、报告和 docs 阶段提交，不触碰 project-manager-agent 的 ops 未完成工作。

## 风险与清退建议

- 旧 roster 记录仍列出 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui`。它们不应再作为活动 agent；若系统中还有旧 unit、锁或旧 PR，应只做归档、关闭或迁移到四个新 agent，不应继续消耗 token。
- `SpellKard` 本地 main ahead 34 是当前最大的版本发布风险，容易让三小时审计无法判断哪些提交已进入远端 CI/PR。
- `Gensoulkyo` 主工作树和 nakama-server-agent worktree 都有未提交服务端改动，且接近鉴权/传输/数据库边界；提交前必须有 `go test`、`docker-compose` 或 protocol audit 证据。
- docs 当前有 project-manager-agent 的 ops 未提交改动；因为它影响 agent 启动、工作树隔离和 systemd 周期，提交前必须至少保留 `py_compile`、manager dry-run、mail dry-run、systemd unit verify 或等价证据。
- battle-server-agent 当前 worktree 已清理为干净，但本地 ahead 4 尚未推送/PR。若后续继续涉及协议、网络、战斗服、鉴权或安全边界，应继续跑 `/root/gotouhou/docs/ops/protocol_audit_check.py`。
- Token 风险仍高：多个 agent 日志已进入数万行/大体量状态。后续报告应只保留提交、测试、阻塞和下一步，避免粘贴长 diff 或长命令输出。

## 测试证据

- 最新 manager 回归摘要（2026-06-30T06:00:23Z）：ok=true、failed=0。
- 已有回归包含 SpellKard Godot headless UI、Boss pattern headless、跨仓 protocol audit、Gensoulkyo `docker-compose config`、PhK-BattleServer `docker-compose config`。
- audit-agent 本轮将运行人格文档最小检查：
  - `python3 -m py_compile ops/goal_agent_manager.py ops/hourly_progress_mail.py`
  - `python3 ops/goal_agent_manager.py --dry-run --root /root/gotouhou`
- 本轮只改 docs 审计报告，不改协议、网络、匹配、战斗服、鉴权或安全代码，因此 audit-agent 自身不触发 protocol audit。

## 下一步

- 恢复 GitHub 连接后重新采样 open PR、CI、behind/dirty 和分支保护状态。
- client-agent：优先处理 SpellKard 本地 main ahead 34 的同步/PR 风险，并继续用 Godot headless 证明 UI/弹幕合同。
- project-manager-agent：完成 docs/ops supervisor 改动的验证、提交和说明，确保 docs agent 用独立 worktree，不再和 audit-agent 在 main 工作树互相踩踏。
- battle-server-agent：推送/开 PR 或说明本地 ahead 4，继续推进 Boss/PVP 1v1 authoritative tick、replay/hash 和结果签名边界。
- nakama-server-agent：清理主 Gensoulkyo 工作树 4 个未提交 Nakama 绑定改动，优先完成 Nakama SDK tag build、PostgreSQL audit wiring 和业务 WSS/RPC envelope 证据。
- audit-agent：三小时邮件正文继续以中文短审计为准，避免把 GitHub 查询失败误报为 open PR 为 0。
