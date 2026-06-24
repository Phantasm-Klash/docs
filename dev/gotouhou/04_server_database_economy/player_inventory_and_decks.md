# 玩家库存与卡组

## 库存

玩家库存记录每张卡：

- copies。
- level。
- first_obtained_at。
- 来源可通过经济流水追溯。

## 卡组

卡组保存：

- deck_id。
- name。
- format。
- card_ids。
- active。
- updated_at。

## 保存校验

保存卡组时检查：

- 玩家拥有所有卡。
- 同名数量不超过限制。
- 卡组数量为 20。
- 禁卡不能进入排位卡组。
- format 与 ruleset_version 兼容。

## 匹配校验

进入匹配时再次校验 active deck。匹配成功后生成 deck_snapshot，当前对局只使用快照。

## 并发

- 卡组保存使用 updated_at 或版本号做并发控制。
- 开箱或掉落获得新卡不影响已开始对局。
- 卡牌被禁用后，保存卡组和进入排位都会失败并返回可展示原因。
