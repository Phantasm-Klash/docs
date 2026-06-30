# audit-agent 阶段审计报告

审计时间：2026-06-30 14:56 UTC

## 总体判断

- docs/dev 主线未变：整体仍按约 38% 估算，当前主线是 Phase 3 服务器权威在线 MVP 与服务拆分收敛；Phase 2/6/8 的客户端、UI、Boss 模式切片仍在并行补齐。
- 当前 open PR 数为 2：Gensoulkyo #28 与 PhK-BattleServer #26 均为 `CLEAN`，各自 2 个 GitHub checks 通过；因为都触及协议/网络/安全敏感面，合并前仍需要人工 diff 审阅和 protocol audit 证据确认。
- 本轮未发现两个 PR 偏离 docs/dev 方向：#28 收紧服务端 HTTP/Nakama callback 与 business envelope 边界，#26 绑定 Boss transfer/result/replay 审计材料和 mode-action authority guard，都在强化服务器权威而非扩大客户端权威。
- 当前最高版本风险不是 PR 冲突，而是根 checkout 状态：`docs` 根仓 `main...origin/main [ahead 1, behind 23]`，`Gensoulkyo` 根仓旧分支 dirty 4，`PhK-BattleServer` 根仓仍在旧 agent 分支。后续新工作应使用 managed worktree 或 current-base 分支，不应把这些根 checkout 当基线。
- 旧 agent 身份 `change-describer`、`gensoulkyo-lobby`、`phk-battle-server`、`plan-auditor`、`spellkard-bullet`、`spellkard-ui` 应继续冻结；只把仍有效的代码或审计证据迁移到五个 managed agents。

## 仓库状态与版本风险

- `docs`：根仓仍在 `main...origin/main [ahead 1, behind 23]`，本地 `b9dee78 ops: summarize agent resource risk` 已被远端后续审计/ops 提交覆盖到主线语义里，但根 checkout 本身仍需由 project-manager-agent 推 PR、同步或重建；本轮 audit-agent 从 `origin/main` 新建 `agent/audit-agent/current-audit-20260630-1455` 工作树，避免继续污染根 `main`。
- `SpellKard`：根仓 `main...origin/main` 干净，当前没有 open PR；client-agent 仍运行中，下一步重点应是把 UI/Boss/Replay 合同继续保持 headless 可验证，而不是重开旧分片式 agent。
- `Gensoulkyo`：根仓仍在旧 `agent/gensoulkyo-lobby/20260629-0900`，dirty 4：`cmd/gensoulkyo_nakama/README.md`、`module.go`、`module_source_test.go` 修改，新增 `module_nakama_test.go`。这些改动看起来围绕 Nakama service-origin callback context vars gate，但 audit-agent 未回滚；应由 nakama-server-agent 在最新 main 上判断吸收、重建或明确废弃。
- `PhK-BattleServer`：根仓仍在旧 `agent/phk-battle-server/20260629-0030` 且干净，不应作为 canonical baseline；battle-server-agent managed worktree 才是后续工作入口。
- `PhK-Protocol`：`main...origin/main` 干净，open PR 为 0；仍需继续把 manifest/JSON bridge 收敛到真实 protobuf Go/C++/Godot 生成物。

## PR 抽审

- Gensoulkyo #28 `Keep HTTP service callbacks out of player envelope guard`：6 个提交，9 个文件，+162/-6。文件面包括 `runtime/httpapi/handler.go`、`runtime/nakamaapi/handler.go`、`runtime/security/business_envelope_adapters.go`、`runtime/core/service.go` 及测试和 README。PR 描述列出 `go test ./runtime/httpapi ./runtime/security`、`go test ./runtime/httpapi ./runtime/core ./runtime/nakamaapi`、`docker-compose --profile test run --rm test`、`protocol_audit_check.py`；GitHub `server-contract-tests` 与 `auto-merge` 均通过。方向符合 Phase 3 的业务服 envelope/callback 安全边界；合并前仍需人工看 diff，特别是 callback allowlist 与 player envelope guard 的绕过条件。
- PhK-BattleServer #26 `Bind Boss transfer aggregate audit material`：3 个提交，9 个文件，+234/-10。文件面包括 `include/phk/battle/result.hpp`、`simulation.hpp`、`src/result.cpp`、`src/server.cpp`、`src/simulation.cpp`、`tests/battle_server_tests.cpp`、`tools/check_battle_server.py`，并同步 `dev/progress.md`、`docs/architecture.md`。PR 描述列出 `docker-compose run --rm test`、`python3 tools/check_battle_server.py`、`protocol_audit_check.py`；GitHub `battle-server-checks` 与 `auto-merge` 均通过。方向符合 C++ 战斗服 result/replay/hash 审计边界；合并前重点看 transfer aggregate 是否只做审计/结果投影，不写库存、奖励、钱包、Steam 或数据库。
- PR 队列采样：`needs_action=0`、`ready=2`、`by_repo={'Gensoulkyo': 1, 'PhK-BattleServer': 1}`、`by_state={'CLEAN': 2}`。这两个 ready PR 仍被 review gate 标记为 `protocol_network_security`，不能仅凭 auto-merge 绿灯跳过审查。

## Agent 采样

- `audit-agent`：running，repo=docs，workdir `/root/gotouhou/docs`，本轮新建 current-base worktree 完成审计报告与 ops 队列分类小修。
- `battle-server-agent`：running，repo=PhK-BattleServer，日志已超过 3MB，资源风险 high；应停止把长日志粘进报告，保持小 PR 与结构化验证。
- `client-agent`：running，repo=SpellKard，日志超过 2.5MB，资源风险 medium；继续要求短切片、headless 检查和及时 PR/提交。
- `nakama-server-agent`：最近一轮 completed，repo=Gensoulkyo，约 652,283 tokens，资源风险 high；下一轮优先处理根 dirty 4 和 #28 合并后的同步。
- `project-manager-agent`：最近一轮 completed，repo=docs，约 317,210 tokens，资源风险 medium；应先修 docs 根 checkout ahead/behind，再继续调度新工作。

## 测试证据

- 本轮 audit-agent 最小检查：`python3 ops/goal_agent_manager.py --dry-run --root /root/gotouhou --no-start` 通过，采样显示 open PR 2、ready 2、repo state risk 5。
- 最新全局回归摘要：2026-06-30T12:00:21Z，`ok=true`、`failed=0`、`ignored=0`。
- 全局摘要包含 SpellKard Godot headless UI/Boss 检查、跨仓 `protocol_audit_check.py`、Gensoulkyo `docker-compose config`、PhK-BattleServer `docker-compose config`；docker 与 `docker-compose` 均可用。
- 本轮只改 docs 审计报告和 ops PR 分类，不改协议、网络、匹配、战斗服、鉴权或安全实现；不额外触发 protocol audit。

## 本轮小切片

- 修正 `ops/goal_agent_manager.py` 的 PR 分类优先级：失败 checks 之后先处理冲突/落后，再优先显示 pending checks，最后才归为 branch/review gate blocked。这样 CI 仍在运行的协议/安全 PR 不会被误报为纯 branch protection 阻塞。
- 刷新三小时审计报告事实：当前只有 Gensoulkyo #28 和 PhK-BattleServer #26 两个 open PR；SpellKard 旧 PR 队列已清空；版本风险转为根 checkout 与旧 dirty worktree 清理。

## 下一步

- nakama-server-agent：优先处理 Gensoulkyo 根 dirty 4；若仍有价值，应在最新 main/current managed branch 上重做为小 PR，并跑 `docker-compose --profile test run --rm test` 与 `protocol_audit_check.py`。
- battle-server-agent：人工审阅并合并 #26 后，同步 managed branch，再推进真实 Ed25519/X25519/KCP/protobuf/AEAD 或 replay/hash golden validation。
- project-manager-agent：清理 docs 根 `ahead 1, behind 23`，不要继续从落后 `main` 生成报告或调度。
- client-agent：保持当前无 open PR 状态，继续用小切片推进正式 UI/Boss/Replay 合同，避免恢复旧 spellkard-bullet/spellkard-ui 分片 agent。
- audit-agent：继续短中文审计 PR、dirty work、测试证据、旧 agent 清退与 token 风险，三小时邮件正文优先使用本报告。
