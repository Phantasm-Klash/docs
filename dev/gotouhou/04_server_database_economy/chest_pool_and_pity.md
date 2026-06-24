# 宝箱池与保底

## 卡池结构

宝箱池包含：

- pool_id。
- season_id。
- name。
- cost_json。
- weights_json。
- pity_json。
- starts_at。
- ends_at。
- enabled。

## 货币和物品

- points：对局积分。
- card_dust：重复卡分解粉尘。
- chest_keys：活动或任务钥匙。
- chests：服务端掉落宝箱。

## 开箱流程

1. 客户端请求 open chest。
2. 服务端检查宝箱池开放、宝箱所有权和钥匙。
3. 服务端扣除成本。
4. 服务端使用 server_seed 生成结果。
5. 服务端写入 chest_openings。
6. 服务端更新库存和钱包。
7. 返回结果展示。

## 保底

开源版初版建议：

- 10 次开箱至少稀有。
- 60 次开箱至少超稀有。
- 活动池保底可继承或不继承，必须在配置中明确。

Steam 商业版可使用 Steam Inventory itemdef 和服务端策略发放宝箱、钥匙和卡牌。具体掉落频率、市场属性和风控不进入开源仓库；开源版只保留本地宝箱池实现。

## 重复卡

- 未满 copies 上限时增加 copies。
- 超出后转为 card_dust。
- 若卡牌等级影响 PVP，排位可统一等级或禁用等级差。

## 审计

每次开箱必须记录成本、seed、结果和时间。客户端展示结果不得反推或重掷。
