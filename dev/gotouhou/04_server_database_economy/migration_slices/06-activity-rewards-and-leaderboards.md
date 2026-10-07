# 06 活动、任务奖励与 Leaderboards

## 目标和边界

把任务进度、活动积分、排行榜读取/领取和奖励幂等迁移到 Nakama
storage、authoritative leaderboard 与 Go Runtime。对局结算由 `05` 产生
进度和排行榜更新；本切片负责读取、资格判断、领取和发奖对账。不负责实时
战斗结算、宝箱随机、商店购买或客户端直接写分。

## 输入、输出和依赖

| 项目 | 规格 |
| --- | --- |
| 输入 | authenticated `user_id`、task/event/leaderboard claim intent、season/event id、幂等键 |
| 输出 | `ActivitySnapshot`、`ActivityClaimResult`、wallet/inventory ledger delta、leaderboard rows |
| 前置依赖 | `01` 身份、`02` economy ledger、`05` verified settlement/outbox、运营配置与时钟 |
| 下游使用者 | Community/Activity UI、bootstrap 聚合、Result 页的 claimable 状态 |
| 实现归属 | `nakama-server-agent`：activity RPC/storage/leaderboard/claim transaction；`client-agent`：活动、任务、排行榜页面 |

## 当前 Gensoulkyo 的岗位

- `Bootstrap` 聚合 `tasks`、`events`、`leaderboards`；默认 task/event/
  leaderboard 状态目前在 core user state。
- settlement `applyProgressLocked` 更新任务进度、活动 points、leaderboard
  rows 和 certification；`activity.claim` 按 `task`、`event`、
  `leaderboard` 判断资格，生成 reward ledger 并标记 claimed。
- 默认排行榜为 `rank_score`、`single_score`、`world_boss_damage`；
  claim 不能由客户端指定分数或 reward。

## 目标 Nakama 契约

### RPC

新增只读 `activity.get`，保留并收紧现有 `activity.claim`：

| RPC | 输入 | 输出 | 错误码 |
| --- | --- | --- | --- |
| `activity.get` | 可选 `season_id`/`event_id` | `ActivitySnapshot`、server time、config version | `unauthorized`, `storage_unavailable` |
| `activity.claim` | `claim_kind`、`claim_id`、幂等键 | `ActivityClaimResult`、wallet/inventory delta、server time | `claim_ineligible`, `already_claimed`, `event_expired`, `revision_conflict` |

`claim_kind` 只允许 `task`、`event`、`leaderboard`。服务端按 Nakama user
identity 查资格；忽略客户端提交的 score、rank、percentile、reward、
wallet 或 progress 字段。相同 `user_id + claim_kind + claim_id + request_hash`
重试返回原结果，不重复发奖。

### Storage

| collection | key | 内容 |
| --- | --- | --- |
| `player_tasks` | `user_id:task_id` | progress、target、period、claimed、config version |
| `player_events` | `user_id:event_id` | points、starts/ends、reward status、config version |
| `activity_configs` | `config_version:event_id` | task/event rules、window、reward table、enabled |
| `activity_claims` | `user_id:claim_kind:claim_id` | request hash、claimed/reward status、settlement key、claimed at |
| `activity_progress_outbox` | `event_id` | verified settlement source、progress delta、apply status |
| `activity_reward_ledger` | `user_id:claim_id` | reward grant、before/after balance hash、idempotency key |
| `leaderboard_profiles` | `leaderboard_id:user_id:season_id` | last verified score、rank snapshot、percentile、updated at |

Nakama authoritative leaderboard ids 固定为：
`rank_score`、`single_score`、`world_boss_damage`。每个赛季/活动使用
metadata 或独立 season suffix 隔离，不能覆盖历史赛季。只有 `05` 的 verified
settlement worker、受控 admin compensation worker 能写分；客户端只能读
leaderboard records 和自己的 snapshot。排行榜领奖状态必须在
`activity_claims`/reward ledger 中维护，不能依赖 Nakama leaderboard row 的
可变 rank。

### Bootstrap 聚合

`bootstrap` 继续返回活动摘要，来源改为 `activity.get` 的同一 repository；
摘要可缓存但必须带 `config_version`、`season_id` 和 `read_source`。活动页面
需要详细数据时调用 `activity.get`，不把完整 leaderboard 列表塞进每次登录。

## 客户端接入点

- `lobby_client.ts` 增加 `getActivity()`、`claimActivity(claimKind, claimId)`
  和按需读取 leaderboard 的方法；所有 claim 请求带业务 envelope/幂等键。
- `lobby_flow.ts` 的 Lobby/Community/Result 页面显示 claimable 状态；领取
  成功后以服务端返回的 wallet/inventory delta 更新本地缓存，再按需刷新
  activity snapshot。
- 新增 Activity/Leaderboard 页面时沿用现有 HTTPS RPC；WSS 可推送
  `activity_updated`/season close 通知，但通知不是奖励凭据。
- UI 对 event start/end、season mismatch、already claimed 和 offline retry
  显示可恢复状态；不能根据本地时钟自行开放或结算奖励。

## 数据迁移

1. 从旧 core user state 导出 task progress、event points/status、
   leaderboard row、season/event config 和已 claim 标志。
2. 先导入 `activity_configs`，校验时间窗口、reward table 与 `05` settlement
   规则版本；再按 `identity_link` 导入玩家进度/claim records。
3. 迁移 leaderboard 时只写当前 verified score 到对应 Nakama authoritative
   leaderboard，并把旧 rank/percentile 留在 `leaderboard_profiles` 作为审计；
   不按旧 rank 直接发奖。
4. 将已发奖励映射到 `activity_reward_ledger`。无法证明已发的记录标记
   `needs_review`，不自动重复发放；新结算 outbox 从切换水位继续消费。

## 回滚策略

- `activity_read_source` 支持 `legacy`、`shadow`、`nakama`；shadow 比较
  task/event/score/claim eligibility，不发奖。
- 切换前冻结活动配置版本和 claim 写入，确保同一 claim 只有一个 authority；
  切回时先停止 Nakama claim，再恢复旧 read/write。
- 已成功 claim 的 reward ledger 不回滚、不重复发放；切回旧系统时把
  `claimed`/ledger 水位导入只读阻断表。排行榜分数以 settlement key 对账，
  不删除 Nakama 记录。
- event/season 关闭后保留历史只读；不通过调整客户端时钟或回滚配置重新开放
  已领取奖励。

## 验收测试

### 服务端

- `activity.get` 只返回当前用户和有效 season/event 的数据；过期活动仍可
  读取历史，但不可新 claim。
- settlement outbox 应用 task/event/leaderboard 更新具备幂等；重复事件不
  增加 progress/score 两次，失败可重试。
- task 未完成、event 不在窗口、leaderboard 未达门槛、已 claim、旧 config
  version 和伪造 reward/score 均稳定拒绝。
- 并发 claim 只有一个成功；重复请求返回同一 `settlement_key`/grant；
  wallet/inventory/activity claim ledger 可审计对账。
- 只有 verified settlement/admin worker 能写 authoritative leaderboard；
  season 隔离、score 方向、tie-break 和历史快照稳定。
- Nakama/PostgreSQL 重启后 claim/outbox/leaderboard 状态恢复；运行
  `docker-compose` 测试、Go Runtime tests 和 protocol audit。

### 客户端

- Activity/Leaderboard 页面能读取任务、活动和三个 leaderboard projection；
  领取成功后只按服务端 grant 更新，不本地计算 reward。
- 双击/断线重试 claim 不重复发奖；已领取、活动过期、版本冲突显示可恢复
  状态。
- 切换 season 后旧 claim/score 不污染新赛季；bootstrap 摘要与 activity.get
  的详细结果一致。

## 明确不在范围内

Steam 商业奖励、商店购买、实时战斗、宝箱开箱、管理员后台 UI 和
leaderboard 算法运营工具不在本切片。

