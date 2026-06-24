# 模式共享服务端接口

## 模式配置

每个模式使用配置驱动：

```json
{
  "mode_id": "battle_royale",
  "mode_ruleset_version": "br_s0_v1",
  "min_players": 5,
  "max_players": 10,
  "card_pool_id": "br_shared_s0",
  "reward_table_id": "br_s0_rewards"
}
```

## Match Handler

所有模式共用权威 match handler 框架：

- `InitModeState`。
- `ValidateJoin`。
- `HandleInput`。
- `HandleModeAction`。
- `AdvanceTick`。
- `BuildSnapshot`。
- `FinalizeMatch`。

各模式只实现差异逻辑。

## 动作类型

- `cast_card`：常规卡牌施放。
- `select_round_card`：大逃杀回合选卡。
- `transfer_card`：Boss 模式让渡卡牌。
- `ready`：准备。
- `reconnect`：重连。

## 持久化

所有模式至少落库：

- match_id。
- mode_id。
- mode_ruleset_version。
- player snapshot。
- seed。
- input stream。
- mode event stream。
- final result。

Boss 模式额外落库 Boss 状态和伤害结算。

## 反作弊

- 客户端不能提交伤害、排名、Boss 扣血、rank 分或奖励结果。
- 大逃杀 3 选 1 候选卡由服务端生成。
- Boss 卡牌让渡由服务端原子处理。
- 考证 top 30% 资格由服务端排行榜计算。
