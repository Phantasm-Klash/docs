# audit-agent 阶段审计报告

审计时间：2026-06-30 08:32 UTC

## 总体判断

- docs/dev 当前主线仍是 Phase 3：Nakama/Go 业务服、C++ BattleServer、PhK-Protocol 共享协议和 SpellKard 客户端投射收敛。服务器权威、协议冻结、持久化、生产传输和正式 UI 仍是最高优先级。
- 最近 agent 提交总体符合 docs/dev 方向：client-agent 继续补 Boss/实例/世界 Boss 展示、服务端结果投射和输入绑定可用性；battle-server-agent 继续补 Boss transfer/replay/hash、match 清退和 start readiness；nakama-server-agent 继续补低频 business.event、Nakama RPC/WSS 合同和审计持久化；project-manager-agent 补三小时邮件 PR 失败可见性。
- 管理面已收敛为 5 个 `/goal` agent：client-agent、battle-server-agent、nakama-server-agent、audit-agent、project-manager-agent。旧 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 仍只应归档，不应重新启动。
- GitHub PR 采样已经可用。本轮 open PR 总数为 11：docs 1、SpellKard 7、Gensoulkyo 2、PhK-BattleServer 1、PhK-Protocol 0。主要问题不是测试缺失，而是旧 PR behind/dirty、branch protection blocked 和本地 ahead 队列未整理。
- 最新回归摘要仍为绿色：2026-06-30T06:00:23Z `ok=true`、`failed=0`。服务端相关 agent 的最近最终日志均记录了 `docker-compose` 和 protocol audit 证据；客户端记录了 Godot headless/static smoke 证据。

## 仓库状态

- `docs`：`main...origin/main [ahead 1]`，工作区在本轮编辑前干净。领先提交为 `f9b6fed ops: force manager proxy for github sampling`；另有 docs PR #20 `ops: show PR collection failures in brief mail`，check 通过但 `mergeStateStatus=BLOCKED`。
- `PhK-Protocol`：`main...origin/main`，工作区干净。最新提交 `b5452af Export golden replay summary fixture (#6)`，符合 v0.1 golden replay/fixture 冻结方向；无 open PR。
- `SpellKard`：`main...origin/main [ahead 34]`，工作区干净。仍是最高版本流风险；同时有 7 个旧 open PR，其中 #19/#17/#14 为 BEHIND，#18/#16/#15/#13 为 DIRTY，虽然各自 CI check 早前通过。
- `Gensoulkyo` 主工作树：`agent/gensoulkyo-lobby/20260629-0900...origin/agent/gensoulkyo-lobby/20260629-0900`，仍有 4 个 Nakama 绑定相关未提交改动。它们靠近鉴权/传输边界，应由 nakama-server-agent 清理、测试、提交或明确废弃，audit-agent 不接管。
- `PhK-BattleServer` 主工作树：`agent/phk-battle-server/20260629-0030...origin/agent/phk-battle-server/20260629-0030`，工作区干净。open PR #14 check 通过且 mergeStateStatus=CLEAN，但尚未合并。

## Agent 采样

- client-agent worktree：`agent/client-agent/persistent...origin/agent/client-agent/persistent [ahead 7]`，工作区干净。最新提交 `35d8251 Expose input binding conflict hints`，本轮 final 记录三个提交：Boss result projection、modes page Boss result contract、input binding conflict hints。验证：`python3 tools/ci_static_checks.py`、`client_smoke_test.gd`、`boss_pattern_catalog_check.gd`、`client_ui_smoke_test.gd` 均通过；未触发 protocol audit。
- battle-server-agent worktree：`agent/battle-server-agent/persistent...origin/agent/battle-server-agent/persistent [ahead 7]`，当前有未提交 `src/server.cpp` 和 `tests/battle_server_tests.cpp`，说明 08:24 后新一轮仍在实现中。上一轮已提交 `b1b4e9e`、`fd246be`、`cfae671`，验证 `python3 tools/check_battle_server.py`、`docker-compose run --rm test`、`protocol_audit_check.py` 通过。不要清退，但应要求本轮结束时提交/测试/推送或写清阻塞。
- nakama-server-agent worktree：`agent/nakama-server-agent/persistent...origin/agent/nakama-server-agent/persistent`，工作区干净且已推送。最新提交 `48331a0 Document business event boundary` 和 `02072f8 Expose business WSS event contract`，验证 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py`、`git diff --check` 通过。PR 创建仍未完成，GitHub open PR 仍是旧 `gensoulkyo-lobby` 分支。
- project-manager-agent worktree：`agent/project-manager-agent/persistent...origin/agent/project-manager-agent/persistent`，工作区干净。PR #20 已创建，check 通过但 blocked。方向正确：三小时简报在 PR 采集失败时列出失败仓库和已采集 PR 数，避免把未知误报成 0。
- audit-agent：本轮更新审计报告和邮件输入，重点是把 08:24 后最新 agent final、open PR 和 worktree 风险写清，供三小时邮件正文优先采用。

## PR 与合并风险

- docs #20：`ops: show PR collection failures in brief mail`，auto-merge check 通过，mergeStateStatus=BLOCKED。需要 branch protection/merge gate 处理。
- SpellKard #13-#19：7 个旧 PR 全部 check 曾通过，但多数 behind/dirty；叠加本地主仓 ahead 34 和 client-agent persistent ahead 7，客户端版本流需要集中整理，不宜继续无限本地堆提交。
- Gensoulkyo #16/#17：均 CLEAN 且 server-contract-tests/auto-merge 通过，但仍未合并。与此同时 nakama-server-agent 新 persistent 分支已推送但未开 PR，主工作树仍 dirty 4。
- PhK-BattleServer #14：CLEAN 且 battle-server-checks/auto-merge 通过，但未合并。battle-server-agent persistent 分支又 ahead 7 且有新未提交改动，需防止旧 PR 与新切片长期分叉。
- PhK-Protocol：无 open PR，当前作为协议 fixture 基线稳定。

## 风险与清退建议

- 不建议清退 5 个新 goal agent；它们均有近期输出或运行状态。需要清退/冻结的是旧 scope roster：`change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 不应再被 manager 启动。
- 版本流最高风险仍是 SpellKard：`main` ahead 34、7 个旧 PR、client-agent persistent ahead 7。下一步应优先做客户端分支/PR 队列整理，而不是继续堆无远端可见提交。
- 服务端风险集中在 Gensoulkyo 主工作树 dirty 4 与 BattleServer persistent 新 dirty 2。两者都靠近协议/网络/鉴权/战斗服边界，提交前必须保留 `docker-compose` 与 protocol audit 证据。
- Token 消耗风险偏高：最近 audit-agent、battle-server-agent 单轮已出现 50 万到 70 万级 token 记录。后续 agent final 和邮件正文必须压缩为提交、测试、阻塞、下一步，不应粘贴长 diff 或长命令输出。
- docs #20 blocked 与 docs `main` ahead 1 会让邮件/manager 改进分散在两个版本流中。建议先处理 docs 版本流，再让 project-manager 继续推进其他仓合并节奏。

## 测试证据

- 最新全局回归摘要：2026-06-30T06:00:23Z，`ok=true`、`failed=0`。
- 回归覆盖：SpellKard Godot headless UI、Boss pattern headless、跨仓 protocol audit、Gensoulkyo `docker-compose config`、PhK-BattleServer `docker-compose config`。
- 本轮 audit-agent 最小检查：
  - `python3 -m py_compile ops/goal_agent_manager.py ops/hourly_progress_mail.py`
  - `python3 ops/goal_agent_manager.py --dry-run --root /root/gotouhou`
- 本轮只更新 docs 审计报告和邮件报告输入，不改协议、网络、匹配、战斗服、鉴权或安全代码，因此 audit-agent 自身不触发 protocol audit。

## 下一步

- project-manager-agent：处理 docs PR #20 blocked，并同步 docs `main` ahead 状态，保证三小时邮件改进进入远端主线。
- client-agent：暂停继续堆大块本地功能，先整理 SpellKard ahead 34、persistent ahead 7 和 7 个旧 PR 的合并/关闭/重建策略。
- battle-server-agent：完成当前 `src/server.cpp` / `tests/battle_server_tests.cpp` 切片，跑 `python3 tools/check_battle_server.py`、`docker-compose run --rm test` 和 protocol audit 后提交。
- nakama-server-agent：为 persistent 分支创建 PR 或说明网络阻塞；清理主 Gensoulkyo dirty 4，继续推进真实 Nakama SDK tag build 与 PostgreSQL repository wiring。
- audit-agent：继续用中文短审计跟踪 PR、dirty work、agent token 和测试证据；三小时邮件只保留结论、风险和下一步。
