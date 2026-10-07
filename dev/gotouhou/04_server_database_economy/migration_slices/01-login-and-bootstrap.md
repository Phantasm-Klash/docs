# 01 登录与 Bootstrap 迁移切片

状态：可实现规格，依赖 Nakama SDK tag-build 环境；不包含代码。

## 范围

本切片迁移匿名登录、外部 Nakama session 到 Gensoulkyo user 的映射，以及
bootstrap 聚合读取：

- `auth.anonymous` RPC；
- `bootstrap` RPC；
- Nakama 用户/session 到业务 `user_id` 的映射；
- 服务端版本、ruleset、模式配置和玩家业务投影的只读聚合。

不在范围内：

- Steam ownership、Steam Inventory 和商业服账号；
- 卡牌/卡组/宝箱/钱包的独立写操作；
- 匹配、房间、battle allocation、战斗结果回调；
- Nakama WSS 推送和业务通知持久化。

Bootstrap 在迁移期间仍返回现有客户端需要的兼容字段。库存、卡组、宝箱
等字段由后续切片提供；在对应切片未切换前，bootstrap 聚合器允许从
Gensoulkyo legacy reader 读取，但禁止客户端看到两套不同的权威值。

## 目标契约

### Nakama RPC

| RPC id | 输入 | 输出 payload | 传输/权限 |
| --- | --- | --- | --- |
| `auth.anonymous` | `AnonymousLoginRequest` | `AuthSession` | 未认证；只允许设备/显示名字段 |
| `bootstrap` | 空对象 | `BootstrapSnapshot` | 已认证；要求 business envelope |

`auth.anonymous` 输入：

```json
{
  "device_id": "spellkard-local",
  "display_name": "Local Tester"
}
```

`AuthSession` 输出字段：

```json
{
  "user_id": "user_x",
  "session_token": "nakama_session_not_persisted_here",
  "display_name": "Local Tester",
  "created_at": "2026-10-07T00:00:00Z"
}
```

生产 Nakama 实现不得把 session token 写入 storage；返回值中的
`session_token` 仅用于兼容现有 HTTP adapter，Nakama 原生客户端使用 Nakama
session token。两种 token 都必须映射到同一个 `user_id`。

`BootstrapSnapshot` 至少保留当前 Go 类型的这些字段：

```json
{
  "user_id": "user_x",
  "session_token": "compatibility_only",
  "display_name": "Local Tester",
  "server_version": "server-v0",
  "ruleset_version": "ruleset-local-s0",
  "modes": [],
  "wallet": {},
  "inventory": {},
  "decks": {},
  "chests": {},
  "tasks": {},
  "events": {},
  "leaderboards": {},
  "certification": {},
  "world_boss": {}
}
```

### Nakama storage

| collection | key | owner | 读写 | 用途 |
| --- | --- | --- | --- | --- |
| `player_profile` | `user_id` | `user_id` | Runtime 读写 | `display_name`、设备/外部 provider 标识、创建与最近登录时间 |
| `player_bootstrap_meta` | `user_id` | `user_id` | Runtime 读写 | `server_version`、`ruleset_version`、`migration_version`、最近聚合时间 |
| `runtime_config` | `server_version:ruleset_version` | 空 | Runtime 只读 | 模式配置、业务 RPC 合同和安全开关 |
| `migration_marker` | `user_id:bootstrap-v1` | `user_id` | Runtime 写入 | 双读/切换阶段、源版本、最后一次校验 hash |

Nakama storage object 的 `version` 必须作为并发条件；profile 和 marker 的写入
使用 `version=""` 只允许创建，已存在对象必须重新读取后用实际 version 更新。

本切片不写 leaderboard。排行榜 id 由后续奖励/评级切片定义，bootstrap 只
聚合已经存在的 server projection。

### 错误码与权威边界

- `invalid_request`：输入 JSON 或显示名不合法；
- `unauthorized`：bootstrap 没有有效 Nakama session；
- `business_envelope_required`：已认证 RPC 缺少 envelope；
- `storage_unavailable`：Nakama storage 读写失败，禁止返回 legacy 与 Nakama
  的混合结果；
- `bootstrap_projection_stale`：聚合校验 hash 不一致，客户端必须重新拉取。

客户端不能提交 `wallet`、`inventory`、`decks`、`chests`、`leaderboards`、
`certification`、`world_boss` 或任何结果/奖励字段作为 bootstrap 输入。

## 客户端接入点

SpellKard 现有入口保持不变：

- `godot/scripts/gensoulkyo_http_client.gd::login_and_bootstrap()`；
- `godot/scripts/gensoulkyo_api_model.gd::anonymous_login_request()`；
- `godot/scripts/gensoulkyo_api_model.gd::bootstrap_request()`；
- `apply_login_response()` 与 `apply_bootstrap_response()`。

迁移适配器应先提供 Nakama RPC transport，再保留 HTTP fallback。Bootstrap
成功后必须把 `user_id`、`server_version`、`ruleset_version` 和各投影按同一
`bootstrap_revision` 应用，禁止先显示本地预测库存或卡组再覆盖。

## 数据迁移与切换

当前 Gensoulkyo 的登录状态位于进程内 `userState`，不能直接当作生产迁移
源。实施前必须由 `nakama-server-agent` 提供一次性导出格式：

```json
{
  "user_id": "user_x",
  "profile": {},
  "bootstrap_meta": {},
  "source_revision": "legacy-<timestamp>"
}
```

迁移步骤：

1. 导出 legacy user snapshot，按 `user_id` 排序并计算文件级 SHA-256。
2. 以 `migration_marker` 为幂等键导入 `player_profile` 和
   `player_bootstrap_meta`；重复执行不得产生第二个用户。
3. 开启 bootstrap 双读：Nakama profile/meta 为主，未迁移用户回退 legacy；
   结果必须带 `migration_stage` 和 `source_revision`，用于审计。
4. 对抽样用户比较 legacy/Nakama 的 `user_id`、显示名、ruleset 和 projection
   hash，连续一轮回归无差异后切换为 Nakama-only。
5. 保留 legacy reader 一个发布周期，删除回退前不得清理导出快照。

## 回滚策略

- 发现 hash、user mapping 或 session 映射错误时，将 `migration_stage` 改为
  `legacy_read_only`，停止 Nakama 写入，不删除已导入 storage。
- HTTP fallback 可继续使用 legacy session；Nakama session 通过
  `player_profile.external_session_ids` 映射回同一 `user_id`。
- 回滚只允许回退 bootstrap/profile 读取；不得回滚已经由后续经济切片提交
  的奖励或战斗结算。
- 修复后从同一 `source_revision` 重跑导入，使用 marker/version 校验，禁止
  盲目覆盖玩家新数据。

## 验收测试

服务端最小命令：

```sh
cd /root/gotouhou/Gensoulkyo
go test ./runtime/... ./cmd/gensoulkyo_nakama
docker-compose --profile test run --rm test
```

必须断言：

- 未认证 `bootstrap` 返回 `unauthorized`；
- `auth.anonymous` 重复导入同一 `device_id` 的策略已明确，不能创建冲突
  profile；
- bootstrap 返回 `user_id`、`server_version`、`ruleset_version`，且所有
  projection 来自同一 revision；
- Nakama storage 暂时不可用时不拼接旧值与新值；
- 重复 migration import 是幂等的，marker version mismatch 会停止写入。

跨仓合同命令：

```sh
python3 /root/gotouhou/docs/ops/protocol_audit_check.py
```

客户端最小命令：

```sh
cd /root/gotouhou/SpellKard
python3 tools/ci_static_checks.py
/root/gotouhou/Godot_v4.7-stable_linux.x86_64 --headless \
  --path godot --script ../tools/client_smoke_test.gd
```

## 依赖与交付边界

- 依赖 `cmd/gensoulkyo_nakama` 的真实 Nakama SDK tag-build；若无法下载
  `nakama-common`，只能记录环境阻塞，不能宣称切片完成。
- 依赖 `02-inventory-and-decks.md` 提供 inventory/decks projection 的 owner。
- 不能要求 battle-server-agent 改动；不能把 battle result 或奖励写入本切片。

