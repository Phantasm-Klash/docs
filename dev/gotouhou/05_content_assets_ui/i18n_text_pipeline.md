# i18n 文本管线

## 目标

所有玩家可见文本独立保存，客户端、服务端和卡牌配置只引用稳定 i18n key。基础主题显示原创文本，东方主题或其他主题通过文本包替换显示，不改变玩法 code。

## 禁止硬编码

代码和配置中禁止硬编码：

- UI 按钮文本。
- 卡牌名称。
- 卡牌描述。
- 机体名称。
- 活动名称。
- 错误提示。
- 奖励说明。
- 主题名。

代码中只允许保存：

- `card_code`。
- `i18n_key`。
- `theme_id`。
- `asset_id`。
- `ruleset_version`。

## 文件结构

```text
client/godot/i18n/
  base.zh-CN.json
  base.en.json
  errors.zh-CN.json
  cards.zh-CN.json
  ui.zh-CN.json
  themes/
    touhou.zh-CN.json
    touhou.en.json
```

## key 命名

```text
ui.main.match
ui.main.deck
ui.main.chests
card.fire_bloom.name
card.fire_bloom.desc
error.deck.invalid_count
theme.base.name
theme.touhou.name
```

## 主题覆盖

基础文本：

```json
{
  "card.generic": "卡牌",
  "resource.energy": "能量"
}
```

东方主题覆盖：

```json
{
  "card.generic": "符卡",
  "resource.energy": "符力"
}
```

## 加载顺序

1. 内置基础语言包。
2. 当前语言补丁。
3. 当前主题文本包。
4. Workshop 主题文本包。

缺失 key 回退到基础语言包，并在开发版输出缺失报告。

## 测试

- CI 检查所有 `i18n_key` 是否存在。
- UI 截图测试检查长文本溢出。
- Workshop Mod 加载时检查 key 冲突和缺失。
- Replay 不保存显示文本，只保存 code 和 key。
