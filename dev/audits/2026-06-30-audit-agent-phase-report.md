# audit-agent 阶段审计报告

审计时间：2026-06-30 08:45 UTC

## 总体判断

- docs/dev 主线仍是 Phase 3：Nakama/Go 业务服、C++ BattleServer、PhK-Protocol 共享协议和 SpellKard 客户端投射收敛。服务器权威、协议冻结、持久化、生产传输和正式 UI 仍是最高优先级。
- 最近提交总体符合 docs/dev 方向：client-agent 推进 Boss/实例/世界 Boss 只读结果投射、输入绑定和 UI 可用性；battle-server-agent 推进 Boss room lifecycle、ready/start guard、replay/hash 和 C++ 权威边界；nakama-server-agent 推进低频 business.event、Nakama RPC/WSS 合同、battle server lifecycle audit 和 service callback gate；project-manager-agent 推进三小时邮件 PR 采集可见性。
- 当前管理面已收敛为 5 个 `/goal` agent：client-agent、battle-server-agent、nakama-server-agent、audit-agent、project-manager-agent。旧 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 只应保留为历史记录，不应重新启动。
- GitHub PR 采样可用。本轮 open PR 总数为 12：docs 1、SpellKard 7、Gensoulkyo 2、PhK-BattleServer 2、PhK-Protocol 0。主要风险不是测试缺失，而是 SpellKard 旧 PR behind/dirty、本地主线 ahead 34、docs #20 behind、以及服务端 agent 新分支和旧 PR 并行。
- 最新全局回归摘要仍为绿色：2026-06-30T06:00:23Z `ok=true`、`failed=0`。服务端相关最终日志和 CI 证据均显示使用 `docker-compose` 或 protocol audit；客户端使用 Godot headless/static smoke。

## 仓库状态

- `docs`：`main...origin/main`，工作区干净。最新提交 `8695bda ops: prefer latest audit report in brief mail` 已在远端主线。open PR #20 `ops: show PR collection failures in brief mail` 仍在 `agent/project-manager-agent/persistent`，当前 `mergeStateStatus=BEHIND`，check 通过但需要更新分支或关闭/重建。
- `PhK-Protocol`：`main...origin/main`，工作区干净。最新提交 `b5452af Export golden replay summary fixture (#6)`；无 open PR，作为当前协议 fixture 基线稳定。
- `SpellKard`：`main...origin/main [ahead 34]`，工作区干净。领先提交集中在 spellbook replay/preview authority、fixture、UI text-fit/focus 等 Phase 2/6 质量收敛；仍是最高版本流风险。另有 7 个旧 open PR：#19/#17/#14 为 BEHIND，#18/#16/#15/#13 为 DIRTY，虽早前 CI 均通过但不适合继续长期堆积。
- `Gensoulkyo` 主工作树：`agent/gensoulkyo-lobby/20260629-0900...origin/agent/gensoulkyo-lobby/20260629-0900`，仍有 4 个 Nakama 绑定相关未提交改动：README、`module.go`、`module_source_test.go` 和新增 `module_nakama_test.go`。改动强化 service-origin callback gate，靠近鉴权/传输边界，应由 nakama-server-agent 清理、测试、提交或明确废弃，audit-agent 不接管。
- `PhK-BattleServer` 主工作树：`agent/phk-battle-server/20260629-0030...origin/agent/phk-battle-server/20260629-0030`，工作区干净。open PR #14 CLEAN 且 check 通过；另有 persistent PR #15 CLEAN 且 check 通过，需决定合并顺序，避免旧 agent 分支与新 goal 分支长期分叉。

## Agent 采样

- client-agent：运行中；worktree 为 `agent/client-agent/persistent`。上一轮 final 记录提交 `ba8853f`、`6108e8b`、`35d8251`，验证 `python3 tools/ci_static_checks.py`、`client_smoke_test.gd`、`boss_pattern_catalog_check.gd`、`client_ui_smoke_test.gd` 通过。当前新一轮仍在跑 Godot smoke。
- battle-server-agent：运行中；worktree 为 `agent/battle-server-agent/persistent`。08:39 采样曾看到 `BuildSignedBattleResultCallback` 失败，08:42 manager dry-run tail 已显示 `python3 tools/check_battle_server.py --build` 通过、CTest 1/1 通过，并进入提交/推送阶段。该 agent 不应清退，但要等待其 final 记录提交、`docker-compose run --rm test` 和 protocol audit 结果。
- nakama-server-agent：运行中；worktree 为 `agent/nakama-server-agent/persistent`。上一轮 final 已推送 `02072f8 Expose business WSS event contract` 与 `48331a0 Document business event boundary`，验证 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py`、`git diff --check` 通过。当前新一轮正在审计旧 Gensoulkyo PR #16/#17 与主树 dirty 改动。
- project-manager-agent：运行中；worktree 为 `agent/project-manager-agent/persistent`。PR #20 已创建但 behind；方向正确，但需避免 docs 主线和 PR 分支长期双轨。
- audit-agent：本轮完成当前采样、最小 ops 检查、中文审计报告和三小时邮件正文更新。

## PR 与合并风险

- docs #20：`ops: show PR collection failures in brief mail`，auto-merge check 通过但当前 BEHIND。由于 `main` 已包含后续 audit/mail 改动，应由 project-manager-agent rebase/refresh，或确认功能是否已被 `8695bda` 覆盖后关闭。
- SpellKard #13-#19：7 个旧 PR 全部已过时。建议 client-agent/project-manager-agent 先做版本流整理：选择保留队列、关闭重复 PR、或重建一个基于最新 main 的综合 PR；暂停继续向本地主线堆无法远端可见的大切片。
- Gensoulkyo #16/#17：均 CLEAN 且 server-contract-tests/auto-merge 通过。若方向无冲突，应优先评审/合并，再处理 persistent 分支新提交和主树 dirty 4。
- PhK-BattleServer #14/#15：均 CLEAN 且 battle-server-checks/auto-merge 通过。#15 是新 persistent 分支，#14 是旧 `agent/phk-battle-server/20260629-0030`；需要按依赖顺序合并或关闭过时分支。
- PhK-Protocol：无 open PR。当前协议仓稳定，但后续 Go/C++/Godot protobuf 真生成仍是 Phase 3 关键空缺。

## 风险与清退建议

- 不建议清退 5 个新 goal agent；它们均在运行或有近期有效输出。应清退/冻结的是旧 scope roster：`change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui`。
- 版本流最高风险仍是 SpellKard：`main` ahead 34、旧 PR 7 个、client-agent persistent 继续工作。该风险已超过功能实现本身，下一步应优先整理合并策略。
- 服务端风险集中在 Gensoulkyo 主树 dirty 4、Gensoulkyo PR #16/#17 未合并、BattleServer #14/#15 并行。两者靠近协议/网络/鉴权/战斗服边界，提交前必须保留 `docker-compose` 与 protocol audit 证据。
- Token 消耗风险偏高：近期 client/nakama/audit 单轮已有 50 万到 70 万级 token 记录。后续 final 和邮件正文必须只保留提交、测试、阻塞、下一步，不应粘贴长 diff 或长命令输出。
- 当前没有证据表明项目停滞；风险是并行 agent 输出过快而版本队列未及时合并，导致后续回归和审计成本上升。

## 测试证据

- audit-agent 本轮已通过：
  - `python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py`
  - `python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start`
- 最新全局回归摘要：2026-06-30T06:00:23Z，`ok=true`、`failed=0`。
- 回归覆盖：SpellKard Godot headless UI、Boss pattern headless、跨仓 protocol audit、Gensoulkyo `docker-compose config`、PhK-BattleServer `docker-compose config`。
- 本轮 audit-agent 只更新 docs 审计和邮件输入，不改协议、网络、匹配、战斗服、鉴权或安全代码，因此自身不触发 protocol audit。

## 下一步

- project-manager-agent：处理 docs #20 behind，并决定关闭、刷新或合并，保证邮件/manager 改进只保留一个版本流。
- client-agent：优先整理 SpellKard ahead 34、persistent worktree 和 7 个旧 PR，而不是继续堆大块本地功能。
- battle-server-agent：完成当前提交/PR 更新后写清 `docker-compose` 与 protocol audit 结果；随后按 #14/#15 顺序合并或关闭旧分支。
- nakama-server-agent：清理主 Gensoulkyo dirty 4；为 persistent 分支创建 PR；继续推进真实 Nakama SDK tag build 与 PostgreSQL repository wiring。
- audit-agent：继续短中文审计 PR、dirty work、agent token、测试证据和旧 agent 清退状态；三小时邮件只保留结论、风险和下一步。
