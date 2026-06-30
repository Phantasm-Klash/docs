# audit-agent 阶段审计报告

审计时间：2026-06-30 09:05 UTC

## 总体判断

- docs/dev 主线未变：当前仍是 Phase 3，重点是 Nakama/Go 业务服、C++ Battle Server、PhK-Protocol 共享协议、SpellKard 客户端投射在服务器权威模型下收敛。服务器权威、协议冻结、持久化、生产传输和正式 UI 仍是最高优先级。
- 最近 agent 输出总体符合方向：client-agent 推进 Boss/实例 Boss 入口和结果只读投射；battle-server-agent 推进 Boss room lifecycle、ready/start guard 和战斗服权威边界；nakama-server-agent 推进入队/房间前 client version/ruleset gate；project-manager-agent 修正三小时邮件 PR 采样和 docs required check 缺席问题。
- 管理面已收敛为 5 个 `/goal` agent：client-agent、battle-server-agent、nakama-server-agent、audit-agent、project-manager-agent。旧 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 只应保留历史记录，不应重新启动。
- 当前 open PR 总数为 10：docs 0、SpellKard 7、Gensoulkyo 2、PhK-BattleServer 1、PhK-Protocol 0。project-manager-agent 已关闭 Gensoulkyo #17 与 BattleServer #14，服务端旧 PR 并行风险下降。
- 最新全局回归摘要仍为绿色：2026-06-30T09:00:24Z `ok=true`、`failed=0`。服务端 agent final 记录均包含 `docker-compose` 或 protocol audit 证据；客户端使用 Godot headless/static smoke。

## 仓库状态

- `docs`：本轮已 fast-forward 到 `ee03d18 ops: show PR collection failures in brief mail`，docs #20 已合并，当前审计在分支 `agent/audit-agent/20260630-0910` 工作，避免继续直接推 `main`。`.github/workflows/protocol-audit.yml` 已取消 PR path 过滤，使 required check `docs-audit` 能覆盖所有 docs PR。
- `PhK-Protocol`：`main...origin/main`，工作区干净，最新主线为 `b5452af Export golden replay summary fixture (#6)`；无 open PR，是当前协议 fixture 稳定基线。后续仍缺真实 Go/C++/Godot protobuf 生成替代临时 manifest/descriptor 桥。
- `SpellKard`：主树 `main...origin/main [ahead 34]` 且干净；client-agent worktree `agent/client-agent/persistent` 相对远端 ahead 9，当前又有 5 个未提交 UI/Boss 状态行改动。7 个旧 PR 仍 open：#19/#17/#14 为 BEHIND，#18/#16/#15/#13 为 DIRTY。
- `Gensoulkyo`：主工作树仍在旧 `agent/gensoulkyo-lobby/20260629-0900` 分支且 dirty 4，涉及 Nakama 绑定 README/module/test。nakama-server-agent worktree已推送 PR #18，但新一轮又出现 `runtime/core/types.go` 未提交改动。
- `PhK-BattleServer`：主工作树在旧 `agent/phk-battle-server/20260629-0030` 分支且干净；battle-server-agent worktree 已推送 PR #15，但新一轮又出现 1 个未提交 simulation header 改动。PR #14 已被 project-manager 关闭，当前只剩 #15。

## Agent 采样

- client-agent：已完成一轮后被 manager 重启；上一轮 final 记录提交 `ea52291`、`f3ae706`，验证 `python3 tools/ci_static_checks.py`、`client_smoke_test.gd`、`boss_pattern_catalog_check.gd`、`client_ui_smoke_test.gd` 通过。当前新一轮正在修改 Boss 状态 UI，尚未 final。
- battle-server-agent：已完成一轮后被 manager 重启；PR #15 包含 `483aaee`、`77b579a`、`e70759b`、`128f925`、`d6e2660`，验证 `python3 tools/check_battle_server.py`、`docker-compose run --rm test`、`protocol_audit_check.py` 通过。当前新一轮正在做 transfer-card authority 相关改动，尚未 final。
- nakama-server-agent：已完成并推送 PR #18；新增入队/房间 `client_version` 兼容性拒绝，验证 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py`、`git diff --check` 通过。方向符合 04 server stack 与协议版本门控。
- project-manager-agent：docs #20 已合并，解决之前 behind 和 required check 缺席问题；随后关闭 Gensoulkyo #17 与 BattleServer #14，减少旧 agent 分支并行。
- audit-agent：本轮完成最新采样、短中文审计报告、三小时邮件正文刷新、ops 最小检查，并改用分支/PR 流程。

## PR 与版本风险

- docs：当前无 open PR；上一轮 direct push bypass 风险已通过本轮审计改用分支/PR 缓解，但仍应避免 agent 直接推 `main`。
- SpellKard #13-#19：全部旧 PR 均过时或冲突。建议 client-agent/project-manager-agent 暂停扩张新功能，先决定保留、关闭或重建一个基于最新 main 的综合 PR；本地 `main` ahead 34 不应继续长期离线堆叠。
- Gensoulkyo #16/#18：均 CLEAN 且 server-contract-tests/auto-merge 通过。#18 是当前 goal agent 正线；#16 来自旧 lobby 分支，合并前需确认与主树 dirty 4 和 #18 无重复/倒退。#17 已关闭。
- PhK-BattleServer #15：CLEAN 且 battle-server-checks/auto-merge 通过，是当前 goal agent 正线。#14 已关闭。
- PhK-Protocol：无 open PR；协议仓暂稳，但 protobuf 真生成仍是 Phase 3 关键空缺。

## 风险与清退建议

- 不建议清退 5 个新 goal agent；它们都有近期有效输出。应冻结旧 scope roster，尤其不要再启动 `gensoulkyo-lobby`、`phk-battle-server`、`spellkard-bullet`、`spellkard-ui` 等旧身份。
- 最高版本风险仍是 SpellKard：本地主线 ahead 34、旧 PR 7 个、persistent 分支 ahead 9。该风险已经高于单点功能缺口。
- 服务端风险集中在 Gensoulkyo 主树 dirty 4、旧 lobby PR #16 与新 #18 并行，以及 battle/nakama 新一轮未提交改动。因涉及协议/网络/鉴权/战斗服边界，提交和合并必须保留 `docker-compose` 与 protocol audit 证据。
- Token 消耗风险偏高：近几轮 client、battle、nakama、audit 单轮常见 27 万到 34 万 token；后续报告应继续短化，减少长 diff/长日志复制。
- 当前没有停滞证据；风险是并行输出快于合并、测试和审计队列，导致后续回归成本上升。

## 测试证据

- 本轮 audit-agent 已通过：
  - `python3 -m py_compile docs/ops/goal_agent_manager.py docs/ops/hourly_progress_mail.py`
  - `python3 docs/ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start`
  - `python3 docs/ops/hourly_progress_mail.py --dry-run --brief --watchdog-summary /root/gotouhou/.agents/last-watchdog-summary.json`
  - `git diff --check`
- 本轮仅更新审计/邮件文档，不改协议、网络、匹配、战斗服、鉴权或安全代码；自身不触发 protocol audit。
- 最新全局回归摘要：2026-06-30T09:00:24Z，`ok=true`、`failed=0`，覆盖 SpellKard Godot headless、跨仓 protocol audit、Gensoulkyo/PhK-BattleServer `docker-compose config`。

## 下一步

- project-manager-agent：继续推动 SpellKard 旧 PR 队列整理；保持旧 agent PR 清退节奏。
- client-agent：优先清理 SpellKard ahead 34、persistent ahead 9 和 7 个旧 PR，而不是继续堆大功能。
- nakama-server-agent：处理 Gensoulkyo 主树 dirty 4；评审/合并 #18 后再判断 #16 是否仍有效。
- battle-server-agent：优先评审/合并 #15；下一切片再补 Boss start 强校验、全员死亡结束或 instance defeat-required 结算互斥。
- audit-agent：继续短中文审计 PR、dirty work、agent token、测试证据和旧 agent 清退状态；三小时邮件只保留结论、风险和下一步。
