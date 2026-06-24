# i18n 与主题包策略

基础游戏使用原创世界观和通用卡牌术语。东方相关文本、美术、音乐和 UI 只作为可替换主题包进入，并优先通过 Steam 创意工坊 Mod 分发。

## 文本原则

- 所有玩家可见文本必须使用 i18n key。
- 玩法逻辑、数据库和网络协议使用稳定 code，不使用显示文本。
- 基础中文文本使用“卡牌”。
- 东方主题中文文本可把同一 key 显示为“符卡”。
- 英文、日文和其他语言与主题独立维护。

## 示例

```json
{
  "card.type.attack": {
    "zh-CN.base": "攻击卡牌",
    "zh-CN.touhou": "攻击符卡",
    "en.base": "Attack Card"
  },
  "deck.builder.title": {
    "zh-CN.base": "卡组构筑",
    "zh-CN.touhou": "符卡组构筑",
    "en.base": "Deck Builder"
  }
}
```

## 主题资源

主题包可替换：

- 文本。
- 角色立绘。
- 自机贴图。
- 弹幕贴图。
- 背景。
- UI 皮肤。
- 音效。
- BGM。

主题包不能替换：

- 碰撞半径。
- 卡牌效果数值。
- 服务器权威规则。
- 掉落概率。
- 市场物品属性。
- 反作弊逻辑。

## 东方主题

东方主题属于高风险主题，需要单独处理：

- 二创规则。
- 商业权益。
- 素材授权。
- 音乐授权。
- 创意工坊审核和下架机制。

基础游戏不内置东方官方素材或未经授权的东方同人素材。东方主题包默认由玩家或授权创作者通过 Workshop 上传，官方仅提供替换接口和审核流程。

## 文件建议

```text
client/godot/i18n/
  base.zh-CN.json
  base.en.json
  theme_touhou.zh-CN.json

client/godot/themes/
  base/
  touhou_placeholder/
  workshop/
```

`touhou_placeholder` 只能放占位结构和示例，不放受版权限制的实际内容。
