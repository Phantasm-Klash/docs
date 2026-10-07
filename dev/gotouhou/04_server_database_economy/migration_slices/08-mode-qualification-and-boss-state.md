# 08 模式资格与 Boss 持久状态

## 目标和边界

把 Gensoulkyo 当前 core 内存中的模式配置、考证资格、世界 Boss 全局血量/
每日次数/击败公告和副本 Boss 入口约束拆到 Nakama/Go Runtime。该切片提供
模式页和匹配入口所需的业务快照，并为 `03` 的入队/建房校验、`05` 的已验签
结算提供可持久化的 mode repository。

本切片覆盖：

- `certification` 的玩家资格/评级资料读取、入场校验和结算后的资料写回接口；
- `battle_royale` 的模式配置、5-10 人入口约束和服务端候选/回合结果的归档
  边界；
- `world_boss` 的 Boss season/instance、全局 HP、每日挑战次数、击败状态和
  一次性世界公告；
- `instance_boss` 的 4-8 人入口配置、按 match 的 Boss 状态索引和
  `defeat_boss` 清除结果投影；
- 模式快照、版本门禁、迁移审计和回滚开关。

明确不在范围内：

- C++ Battle Server 的 60Hz 输入、弹幕、碰撞、卡牌效果和实时模式状态；
- `select_round_card`、`transfer_card` 等高频 `mode_action` 的战斗传输；
- signed battle result 的验签、奖励 ledger、Replay 和通用排行榜写入；
- Steam 赛季、商业奖励、市场或闭源 Boss 配置。

`mode_action` 的迁移结论固定为：旧 Gensoulkyo HTTP 端点只作为契约回退；
生产客户端经 Battle KCP/UDP 向 C++ Battle Server 发送 intent，Nakama 只接收
`05` 已验签的模式结果和只读业务通知。不得新增玩家可直接调用的
`mode.action` Nakama RPC 来绕过战斗服权威。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | authenticated `user_id`、`mode_id`、`season_id`、`mode_ruleset_version`、active deck snapshot hash、已验签 `match_id`/result projection |
| 输出 | `ModeSnapshot`、`ModeEntryDecision`、`CertificationProfile`、`WorldBossSnapshot`、Boss settlement apply receipt、模式审计事件 |
| 前置依赖 | `01` 身份与 `identity_link`、`02` canonical deck、`03` roster/模式入队、`04` allocation/ticket、`05` signed result callback、PhK-Protocol battle/result 字段 |
| 并行依赖 | `06` 读取 `rank_score`/`world_boss_damage` 的 leaderboard projection；`nakama-server-agent` 与 `client-agent` 可按本文件并行实现 |
| 输出消费者 | `03` 的 Go Runtime 入场校验、`05` 的 settlement transaction、`SpellKard` 模式页/结果页、bootstrap 摘要 |
| 实现归属 | `nakama-server-agent`：RPC、storage、条件写、mode policy、迁移/回滚；`client-agent`：快照读取、入口状态、结果投射和 KCP intent 接入 |

## 当前 Gensoulkyo 的岗位

代码对照以当前 `Gensoulkyo` core 为准：

- `runtime/core/types.go`
  - `ModeConfigs` 定义 `certification`、`pvp_duel`、`battle_royale`、
    `world_boss`、`instance_boss` 的人数、mode ruleset 和 reward table；
  - `CertificationProfile` 和 `WorldBossSnapshot` 进入 `BootstrapSnapshot`；
  - `ModeActionRequest/Response` 描述客户端 intent 和服务端确认投影。
- `runtime/core/service.go`
  - `validateLoadout` 和 `validateModeEntryLocked` 校验评级参数、模式和
    world Boss 当前 HP/每日次数；
  - `ensureWorldBossLocked`、`worldBossAttempts`、`consumeModeEntryLocked`
    维护当前进程内的 Boss 状态；
  - `applyWorldBossModeStateLocked` 输出 Boss HP/次数/公告字段；
  - `finalizeModeResultLocked` 把验收后的团队伤害应用到全局 HP，并只发出一次
    `world_boss_defeated`；
  - `applyBossTransferLocked`、`applyBattleRoyaleSelectionLocked` 处理
    mode action，但这些应由 C++ 战斗服承接实时权威；
  - `buildSettlementLocked` 和 `applyProgressLocked` 派生考证、Boss、奖励和
    leaderboard projection，实际落库由 `05`/`06` 分工。
- `runtime/nakamaapi/handler.go`
  - 当前 Nakama adapter 已能转发 bootstrap、匹配、battle allocation/ticket、
    activity 和 service callback；本切片增加 `modes.get`，不注册玩家
    `mode.action`。
- `SpellKard`
  - `godot/scripts/gensoulkyo_http_client.gd` 和
    `godot/scripts/gensoulkyo_api_model.gd` 消费 bootstrap、mode action 和
    settlement；
  - `godot/scripts/game_mode_model.gd` 保存 certification/world Boss/
    instance Boss 状态和客户端显示策略；
  - `godot/scripts/network_match_model.gd` 与
    `godot/scripts/battle_network_client_model.gd` 构造战斗层
    `mode_action` intent；
  - `tools/gensoulkyo_live_http_check.gd`、`tools/client_smoke_test.gd` 已覆盖
    入口约束、候选卡、Boss transfer、全局 HP、每日次数和服务端结果拒绝。

## 目标 Nakama 契约

### 玩家 RPC

保留 bootstrap 中的 `certification`/`world_boss` 摘要，同时新增一个按需读取
的 authenticated custom RPC：

| RPC | 输入 | 输出/副作用 | 权限 |
| --- | --- | --- | --- |
| `modes.get` | 可选 `mode_ids[]`、`season_id`、`known_mode_config_version` | `ModeSnapshot`，包含配置、资格、Boss 摘要、read source 和 server time | 玩家 session；owner 由 session 决定 |

请求示例：

```json
{
  "mode_ids": ["certification", "battle_royale", "world_boss", "instance_boss"],
  "season_id": "local_s0",
  "known_mode_config_version": "mode-config-local-s0-v1"
}
```

响应至少包含：

```json
{
  "ok": true,
  "server_authoritative": true,
  "mode_config_version": "mode-config-local-s0-v1",
  "ruleset_version": "ruleset-local-s0",
  "server_time": "2026-10-07T00:00:00Z",
  "modes": [
    {
      "mode_id": "world_boss",
      "mode_ruleset_version": "world-boss-s0",
      "min_players": 4,
      "max_players": 8,
      "entry_status": "eligible",
      "entry_reason": "none",
      "state": {}
    }
  ],
  "certification": {},
  "world_boss": {},
  "read_source": "nakama"
}
```

`state` 只包含客户端展示和 `03` 入场所需字段，不包含客户端可写的分数、
伤害、奖励、Boss HP 结果或候选卡最终归属。错误码固定为：
`unauthorized`、`mode_not_found`、`season_mismatch`、
`mode_config_unavailable`、`storage_unavailable`、`version_mismatch`。

### 内部 Go Runtime 面

这些不是玩家 RPC，而是 `03`/`05` 依赖的同一 mode repository 接口：

| 内部操作 | 输入 | 输出 | 原子要求 |
| --- | --- | --- | --- |
| `ValidateModeEntry` | user、mode、deck snapshot hash、season/config version | eligible/rejected、reason、locked config hash | 不写资产；world Boss 只在 match 进入 server-owned combat 时消耗次数 |
| `LockModeRoster` | match id、mode、players、config hash | locked mode snapshot | match 只绑定一个 mode/ruleset/config |
| `ApplyVerifiedModeSettlement` | `match_id`、signed result hash、mode projection | apply receipt、duplicate/rejected | 同一 settlement key 只应用一次 |
| `GetModeSnapshot` | user、mode/season | 只读快照 | 读取失败不可伪造默认奖励或资格 |

`03` 只调用 `ValidateModeEntry`/`LockModeRoster`；`05` 先完成 battle result
验签，再调用 `ApplyVerifiedModeSettlement`。客户端传入的 `rating_code`、
`boss_hp_after_global`、`boss_damage`、`instance_cleared`、`rank_score_delta`、
`reward_grants` 和 `world_announcement` 一律忽略或拒绝。

### 模式具体约束

| 模式 | Nakama/Go 负责 | Battle Server 负责 | 结果交接 |
| --- | --- | --- | --- |
| `certification` | season、rating code、rank score floor、challenge stage、entry eligibility | 对局内战斗与确定性结果 | `05` 验签后更新 `player_certification`，由 `06`/verified worker 更新 `rank_score` |
| `battle_royale` | 5-10 人配置、card pool/config hash、entry gate、locked roster | 候选生成、30 秒窗口、3 选 1、公共池、zero-round 顺序 | `05` 归档 round/public-pool summary；不从客户端接收最终排名 |
| `world_boss` | season/instance、全局 HP、每日次数、entry gate、一次性公告状态 | 4-8 人战斗、伤害、transfer intent、战斗 replay | `05` 验签后原子扣减 global HP；`06` 写 `world_boss_damage` projection |
| `instance_boss` | 4-8 人配置、entry gate、clear policy/config | per-match HP、阶段、transfer intent | `05` 只接受 server-owned `instance_cleared`，未击败必须为 failed |

### Storage collection/key

| collection | key | 内容 | 写入者 |
| --- | --- | --- | --- |
| `mode_configs` | `mode_config_version:mode_id` | mode ruleset、人数、card pool、reward table、entry/clear policy、config hash、active window | 受控 Go config loader |
| `player_certification` | `user_id:season_id` | rating code、rank score、floor、challenge stage、percentile、top-30 flag、last settlement key、updated at | `05` verified settlement transaction |
| `world_boss_state` | `season_id:boss_instance_id` | max/current HP、starts/ends、defeated at、defeated match/user、announcement key/status、revision | `07` repository；只接受 `05` 已验签写入 |
| `world_boss_attempts` | `season_id:utc_day:user_id` | used count、last match id、entry reservation/apply status、revision | `07` entry/settlement transaction |
| `world_boss_contributions` | `season_id:boss_instance_id:match_id:user_id` | verified team/player damage、before/after HP、result hash、settlement key、applied/duplicate | `05`/`07` settlement bridge |
| `instance_boss_runs` | `match_id` | season/config hash、roster、server result hash、HP/phase summary、clear status、stars projection | `05` verified settlement |
| `mode_entry_audit` | `event_id` | user/match/mode、decision、reason、config hash、source hash、migration batch | `03`/`07` |
| `mode_migration_batches` | `migration_batch_id:user_id` | source/target snapshot hash、version、status、rejected reason、checked at | 迁移工具/Runtime |

Storage 写入必须使用 Nakama storage version/conditional write 或事务型
repository。`world_boss_state.current_hp` 只能使用 compare-and-swap：
`expected_revision + applied_damage`，禁止“读后写”覆盖并发队伍的伤害。
每日次数必须以 `season_id + UTC date + user_id` 为唯一键；同一 match 重试只
返回原 apply receipt。

### Leaderboard 面

本切片不直接接受客户端 leaderboard write，也不把模式状态当分数写入：

- `rank_score`：由 `05` 的已验签 certification settlement 产生，
  `06` 负责 season projection/读取/claim；
- `world_boss_damage`：由 `05` 的已验签 Boss result 产生，`07` 只提供已应用
  contribution 和 before/after HP 作为写入依据；
- `single_score`：沿用 `05` 的通用结算路径；
- battle royale 排名若尚未有现成 Gensoulkyo leaderboard，不在本切片虚构新的
  玩家写入口；先保存 signed result 的 round/rank summary，待 `06` 定义赛季榜
  id 后再接 authoritative leaderboard。

## 客户端接入点

### 模式快照和入口

- `godot/scripts/gensoulkyo_http_client.gd`
  - 增加 Nakama HTTPS `modes.get` 调用，业务 envelope 的 `op` 固定为
    `modes.get`；
  - bootstrap 的 mode 摘要仍可用于首屏，进入 Modes/Certification/Boss
    页面时按需刷新；
  - `mode_config_version`、`ruleset_version`、`entry_status` 不匹配时停留在
    mode-select，不发起匹配。
- `godot/scripts/gensoulkyo_api_model.gd`
  - 把 `ModeSnapshot` 投射到 `game_mode_model.gd`；
  - 保存 `read_source`、`server_time`、`entry_reason`、Boss revision 和
    `server_authoritative`，不接受本地覆盖 HP、rank 或 reward。
- `godot/scripts/game_mode_model.gd`
  - certification 页显示 rating/rank/top-30/next stage；
  - world Boss 页显示 global HP、daily attempts、season/window、公告状态；
  - instance Boss 页显示 party gate、clear policy 和 server receipt 状态；
  - battle royale 页显示人数/card pool/config hash，候选和选择结果只消费
    Battle Server packet/event。

### 战斗动作和结果

- `godot/scripts/battle_network_client_model.gd` 使用
  `mode_action` KCP/protobuf intent：
  `select_round_card` 只提交 `round_index + candidate_index/card_id`，
  `transfer_card` 只提交 `to_player_id + card_id`；不提交 damage/HP/rank/
  reward/result。
- `godot/scripts/network_match_model.gd` 和
  `godot/scripts/gensoulkyo_http_client.gd` 保留旧 HTTP mode-action 仅作
  migration fallback/live check；Nakama 主路径不得把它当结算来源。
- Result 页面通过 `05` 的 `settlement`/`replay.get` 回执更新
  `game_mode_model`；重复通知按 settlement key 去重，不能本地应用世界 Boss
  扣血或 certification 加分。
- 相关客户端验证入口：
  `tools/gensoulkyo_live_http_check.gd`、`tools/client_smoke_test.gd`、
  `tools/latency_matrix_check.gd`。这些测试需增加 Nakama `modes.get` 解析和
  stale snapshot/authority boundary 断言，但不把高频 mode action 改成 HTTPS。

## 数据迁移

### 导出和映射

1. 从 Gensoulkyo 导出 `ModeConfigs` 版本、用户 `CertificationProfile`、
   `worldBossState`、`worldBossAttempts`、已结束 Boss match projection、
   mode audit；不导出 session token、设备原始标识或任何客户端提交结果。
2. 以 `01` 的 `identity_link` 将 legacy user 映射为 Nakama `user_id`。无法
   唯一映射的 certification/attempt 进入 `rejected`，不能按 display name
   猜测归属。
3. 先导入 `mode_configs`，再导入 `player_certification` 和
   `world_boss_state`，最后导入 daily attempts/contribution/audit。顺序保证
   入口校验不会读取半套配置。
4. `world_boss_state` 必须保存 `source_snapshot_hash`、`target_revision`、
   `last_applied_settlement_key` 和 `announcement_key`。已击败 Boss 的
   `current_hp=0` 与公告状态必须同时校验，不能只迁 HP。
5. 对 `instance_boss_runs` 只迁移已有 signed/verified result；只有客户端
   声称击败但没有 Battle Server result hash 的记录进入 `needs_review`。

### 双读和切换水位

- `legacy` 阶段旧 core 是读写权威；
- `shadow` 阶段 Nakama 计算 mode snapshot/entry decision，并比较
  `mode_config_hash`、certification profile、Boss HP/revision、daily attempt
  count 和 announcement key，只写 audit；
- `nakama` 阶段每个 mode/season 只有一个写权威；切换记录
  `migration_batch_id`、`cutover_event_id`、`source_watermark` 和
  `target_revision`；
- 活跃 world Boss match 在切换窗口内必须完成 legacy settlement 或被标记
  `migration_pending`，不得让同一 match 同时扣旧/新 HP。

## 回滚策略

- `mode_authority` 支持 `legacy`、`shadow`、`nakama`，按
  `mode_id + season_id` 配置，禁止对同一 Boss instance 同时双写；
- Nakama 读失败可回到 legacy snapshot，但不能回滚已成功应用的
  `world_boss` settlement；以 `settlement_key` 和 `world_boss_contributions`
  对账后再处理未应用 outbox；
- world Boss HP 一旦由已验签结果从 `before_revision` 应用到
  `after_revision`，回滚不得把 HP 加回去，也不得重复发
  `world_boss_defeated` 公告；纠错只能新增补偿审计；
- certification 已写入的 rank 变化不删除，回滚只暂停新结算并切换未处理
  match；`player_certification.last_settlement_key` 防止重复应用；
- instance Boss 的已完成/失败 run 保留只读，回滚不能把 server-owned
  `instance_cleared` 改为客户端可重试的成功；
- config/hash 不一致时关闭对应 mode entry，返回 `version_mismatch` 或
  `migration_not_ready`，不降级到客户端默认 HP、rank 或奖励。

## 验收测试

### 服务端

- `modes.get` 只返回当前 session 可见的 mode/config/profile/Boss snapshot；
  伪造 user id、season、owner key、rank、HP 或 reward 字段不能改变结果。
- `certification` 的入场校验拒绝错误 rating code、旧 config/ruleset 和不合格
  profile；verified settlement 只应用一次，重复 result hash 返回 duplicate。
- `battle_royale` 只返回 5-10 人和 card-pool/config hash；Nakama 不接受
  `candidate_cards`、round selection 或最终排名作为玩家写入。
- world Boss 在同一 revision 并发应用时只有一个 CAS 顺序成功；重复
  `settlement_key` 不重复扣 HP、次数或公告；HP 到 0 只产生一个
  `announcement_key`。
- 每日次数按 UTC day 隔离；未进入 server-owned combat 不消耗次数，重连/重复
  `match_start` 不重复消耗；HP 为 0 或次数耗尽拒绝新入口。
- instance Boss 未满足 `defeat_boss` 的 verified result 只能得到 failed；
  客户端提交 `instance_cleared=true`、Boss HP 或 stars 被拒绝。
- Nakama/PostgreSQL 重启后 mode config、cert profile、Boss HP/revision、
  attempts、contribution 和 audit 可恢复；leaderboard 暂不可用时
  settlement/contribution 仍可重试。
- 最小本地 core/adapter 命令：

  ```sh
  cd /root/gotouhou/Gensoulkyo
  go test ./runtime/core ./runtime/nakamaapi ./runtime/httpapi
  ```

- Nakama/PostgreSQL 优先使用 `docker-compose`：

  ```sh
  cd /root/gotouhou/Gensoulkyo/deployments/nakama
  ./build-plugin.sh
  docker-compose up -d
  docker-compose ps
  ```

- 协议/网络/安全门禁：

  ```sh
  python3 /root/gotouhou/docs/ops/protocol_audit_check.py
  ```

### 客户端

- `modes.get` 返回的五个模式和 `mode_config_version` 能被
  `game_mode_model` 解析；过期 config、缺 Boss revision、非 server-authoritative
  快照停留在可恢复 mode-select 状态。
- Certification 页面展示 server rating/rank/top-30，不根据本地分数开放
  下一阶段；World Boss 页面显示 HP/attempts/公告，刷新后与服务端一致。
- Battle Royale 客户端只发送合法 `mode_action` intent；不把候选、公共池、
  排名或 reward 放进 Nakama RPC；重复选择由服务端拒绝且不重复更新 UI。
- Boss transfer 在 30/80/150/250ms、断线重连和重复点击下只产生一个
  action/receipt；客户端不直接改 card ownership 或 Boss HP。
- Result/Replay 页面只接受 `05` signed settlement projection；伪造或缺 hash
  的 world/instance Boss result 显示 rejected，不进入可信结果状态。
- 最小 Godot 检查：

  ```sh
  cd /root/gotouhou/SpellKard/godot
  /root/gotouhou/Godot_v4.7-stable_linux.x86_64 --headless --path . --script ../tools/client_smoke_test.gd
  ```

  迁移期 HTTP live check 仍可执行：

  ```sh
  cd /root/gotouhou/SpellKard/godot
  /root/gotouhou/Godot_v4.7-stable_linux.x86_64 --headless --path . --script ../tools/gensoulkyo_live_http_check.gd
  ```

## 明确不在范围内

`05` 负责 signed result 验签、settlements/replays/reward outbox；`06` 负责
leaderboard projection、activity claim 和赛季读取；Battle Server agent 负责
高频 mode action、候选生成、Boss tick/transfer、最终状态 hash。Nakama
server agent 本切片不得实现第二套战斗模拟或允许玩家直接写 Boss/rank/result。

## 实现完成判定

服务端 agent 能证明 mode snapshot、entry decision、certification profile、
world Boss HP/attempts/announcement 和 instance clear policy 都有唯一
Nakama/PostgreSQL owner、版本和条件写路径；并能按 settlement key 重放而不
重复扣 HP、发公告或改变评级。client agent 能只通过 `modes.get` 和
`05` settlement projection 完成模式页、入口门禁、结果/Replay 展示，并把
实时 mode action 留在 Battle KCP/UDP intent 通道。
