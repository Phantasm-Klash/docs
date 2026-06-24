# 07 Steam Closed Layer

本目录描述 Steam 商业发行版的闭源适配层边界。这里的文档只写接口、流程和验收目标，不写 Steam Web API Key、publisher key、掉落风控参数、市场策略细节或任何敏感配置。

## 定位

Steam 版是买断制网游，没有游戏内充值和内购。玩家购买游戏后进入官方商业服。官方商业服可以通过服务端对局、活动或成就式条件发放宝箱、钥匙、卡牌或外观，这些物品可按 Steam Inventory 配置决定是否可交易或可在 Steam 市场流通。

## 闭源内容

- Steam 登录和购买校验。
- Steam 成就和统计。
- Steam 创意工坊 Mod。
- Steam Inventory 掉落、开箱和物品同步。
- Steam 市场可交易物品策略。
- 商业服风控和反刷。

## 开源核心接口

开源核心只暴露平台抽象接口：

- `PlatformAuthProvider`。
- `PlatformOwnershipProvider`。
- `PlatformAchievementProvider`。
- `PlatformWorkshopProvider`。
- `PlatformInventoryProvider`。

开源版提供空实现或本地实现，Steam 版由闭源模块实现。

## 验收

- 未购买 Steam App 的账号无法进入官方商业服。
- Steam 玩家可以正常映射到游戏账号。
- 成就可同步。
- Workshop 主题包可订阅和启用。
- Inventory 物品发放、开箱、交易属性和市场状态可查询。
- Steam 敏感配置不进入 GitHub。
