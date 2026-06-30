# audit-agent 阶段审计报告

审计时间：2026-06-30 04:05 UTC

## 结论

- 当前 docs/dev 主线仍是 Phase 3：Nakama/Go 业务服 + C++ BattleServer + PhK-Protocol 共享协议 + SpellKard 客户端投射，服务器权威与协议审计优先。
- 新 `/goal` agent 模型已生效；本轮采样初始显示 4 个新 agent 运行，后续 dry-run 显示 client-agent 已完成，battle-server-agent、nakama-server-agent、audit-agent 仍在运行。
- 旧 scope roster 仍有历史记录：change-describer、gensoulkyo-lobby、phk-battle-server、plan-auditor、spellkard-bullet、spellkard-ui。它们不应继续作为调度主体；若仍有残留锁或旧 PR，需要 manager 明确清退或归档。
- 各仓近期提交方向总体符合 docs/dev：SpellKard 聚焦客户端 UI/Replay/spellbook 权威展示，Gensoulkyo 聚焦 Nakama callback/envelope/audit，PhK-BattleServer 聚焦 KCP/加密边界和 replay/hash，PhK-Protocol 已补 golden replay/snapshot/mode-action fixture。
- PR 实时查询被本机 socks5h 代理连接失败阻塞，不能把当前 open PR 视为 0；上一份本地审计曾记录 open PR 10 个，下一轮必须恢复 GitHub 查询后复核。

## 仓库与分支

- docs：`main...origin/main`。存在已 staged 的 ops 迁移改动：`ops/README.md`、`ops/goal_agent_manager.py`、`ops/hourly_progress_mail.py`、`ops/hourly_progress_runner.sh`，以及未跟踪 systemd/runner 文件。审计没有回滚或接管这些改动。
- SpellKard：`main...origin/main [ahead 34]`，工作区干净。风险是本地 main 长期领先远端，且上一份报告显示 SpellKard 旧 PR 多数 behind/dirty，需要整理为可审查分支或推送同步。
- Gensoulkyo：`agent/gensoulkyo-lobby/20260629-0900...origin/agent/gensoulkyo-lobby/20260629-0900`，当前分支相对 `origin/main` ahead 41。存在未提交 Nakama service-origin callback gate 加固，方向符合 Phase 3 安全边界，但必须由 nakama-server-agent 自己完成测试、提交和 PR/说明。
- PhK-BattleServer：`agent/phk-battle-server/20260629-0030...origin/agent/phk-battle-server/20260629-0030`，工作区干净，相对 `origin/main` ahead 47。近期提交集中在 decoded packet、reconnect cursor、encrypted session guard，符合 C++ 战斗服边界推进。
- PhK-Protocol：`main...origin/main`，工作区干净。最新提交包含 golden replay summary fixture，符合冻结 v0.1 协议和跨仓 audit 的方向。

## Agent 状态与风险

- client-agent：本轮已完成提交 `9c1d1af Harden Boss result authority projection`，并报告通过 static/Godot/protocol audit。仍需处理 SpellKard 本地 main ahead 35 左右的版本流风险。
- battle-server-agent：运行中，方向集中在 C++ 战斗服传输/加密/replay 边界；协议/网络/安全改动必须继续跑 protocol audit。
- nakama-server-agent：运行中，正在收紧 Nakama service-origin callback gate；这是安全边界改动，必须跑 `go test`、docker-compose profile 或 protocol audit 后提交。
- audit-agent：本轮完成中文审计报告并提交 docs 侧报告文件。
- Token 风险：四个 agent 日志体量已超过 1.5 MB，client-agent 本轮报告约 102k tokens。后续应要求各 agent 更早提交小切片、缩短日志输出、在报告中只写证据摘要。

## 测试证据

- 最新 `.agents/checks/latest-regression.json` 显示 ok=true、failed=0。
- 已有回归包含 SpellKard Godot headless UI、Boss pattern headless、跨仓 protocol audit、Gensoulkyo docker-compose config、PhK-BattleServer docker-compose config。
- 本轮 audit-agent 已按人格最小验证运行：
  - `python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py`
  - `python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou`
- 因本轮只新增审计报告，未改协议、网络、匹配、战斗服、鉴权或安全代码，本轮 audit-agent 自身不触发 protocol audit；Gensoulkyo 未提交安全改动应由对应 agent 触发。

## 下一步

- 恢复 GitHub PR 查询后复核 open PR、behind/dirty、CI 状态和是否需要合并或关闭旧 PR。
- manager 侧清理旧 scope 调度痕迹，确保只保留四个新 agent，旧 roster 不再触发。
- SpellKard 需要优先处理本地 `main` ahead 34 的版本流风险：推送、拆 PR，或说明为何保持本地队列。
- Gensoulkyo 当前 service-origin callback gate 改动应尽快提交，并附 go test/docker-compose/protocol audit 证据。
- Phase 3 主线继续压实协议冻结、Nakama SDK tag build、PostgreSQL audit wiring、BattleServer 真实 protobuf/KCP/AEAD、SpellKard battle client 绑定。
