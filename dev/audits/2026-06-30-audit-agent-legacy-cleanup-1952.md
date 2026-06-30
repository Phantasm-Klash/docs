# audit-agent legacy cleanup audit 2026-06-30 19:52 UTC

## 结论

- 最新 dry-run：`agent_health.score=82`、open PR=0；主阻塞已从 PR 队列转为旧 root checkout 清退和运行中 agent 的新切片收敛。
- Gensoulkyo `agent/gensoulkyo-lobby/20260629-0900` dirty=4 仍需处理，但核心改动已被 `origin/main` 的 #47 更完整覆盖。
- PhK-BattleServer root 仍在 `agent/phk-battle-server/20260629-0030` legacy 分支，和 main 差异约 16 文件/4036 行新增，不能当作当前基线。

## Gensoulkyo legacy dirty 判断

- dirty 内容：`cmd/gensoulkyo_nakama/README.md`、`module.go`、`module_source_test.go`、未跟踪 `module_nakama_test.go`。
- 方向：更严格限制 service-origin callback，要求 `runtime.RUNTIME_CTX_MODE=rpc`，并要求 `RUNTIME_CTX_VARS` 带 `gensoulkyo_service_origin=battle_server` 与 `gensoulkyo_battle_callback=true/1/yes`。
- main 现状：#47 已合并，`module.go` 已改为从 `core.ServiceCallbackContext()` 和 `core.ServiceCallbackAcceptedValues()` 读取 accepted values，比 legacy dirty 的硬编码常量更符合共享合同方向。
- 建议：不要提交整个 legacy dirty；只由 nakama-server-agent 评估未跟踪 `module_nakama_test.go` 的 build-tagged 运行时测试是否还有补充价值。如保留，应基于当前 main 重写测试，并跑 `go test ./runtime/... ./cmd/gensoulkyo_nakama`、`docker-compose --profile test run --rm test`、protocol audit。

## PhK-BattleServer legacy branch 判断

- root 分支：`agent/phk-battle-server/20260629-0030`，相对 main 包含 KCP/decoded dispatch/replay/result/signature/simulation 大量旧提交。
- 差异体量：`dev/progress.md`、server/simulation/result/kcp/protocol/tests/checker 等 16 文件，约 4036 行新增。
- 风险：体量过大且与已合并的 #48/Boss lifecycle 路线可能重叠，不能直接 merge/cherry-pick；继续以 root legacy 为基线会放大冲突和 token 风险。
- 建议：保持 frozen。battle-server-agent 只从 managed branch 或最新 `origin/main` 继续；若要迁移旧分支内容，应拆成单一主题 PR，例如 decoded packet adapter、replay bridge、signature boundary，每个 PR 单独跑 `python3 tools/check_battle_server.py`、`docker-compose run --rm test`、protocol audit。

## 下一步

1. nakama-server-agent：清退 `agent/gensoulkyo-lobby/20260629-0900` dirty，默认 supersede；仅保留可重写的 build-tag test 思路。
2. battle-server-agent：不要使用 root legacy 分支，按主题拆迁移旧工作。
3. manager/audit：下轮 summary 若 open PR=0 仍出现旧 PR 队列，应以 normal resample 覆盖，不使用旧 dry-run 作为权威 watchdog 状态。
