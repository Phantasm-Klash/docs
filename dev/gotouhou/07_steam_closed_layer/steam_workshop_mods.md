# Steam 创意工坊 Mod

## 目标

通过 Steam Workshop 分发主题包，包括东方主题和其他玩家创作主题。主题包只替换文本、美术、音频和 UI 皮肤，不改变服务器权威玩法规则。

## Mod 内容

允许替换：

- i18n 文本。
- 角色立绘。
- 自机和弹幕贴图。
- 背景。
- UI 皮肤。
- 音效和 BGM。

禁止替换：

- 卡牌数值。
- 碰撞半径。
- 掉落概率。
- 服务器规则。
- 反作弊逻辑。

## manifest

每个 Workshop Mod 必须包含：

```json
{
  "mod_id": "steam_workshop_id",
  "theme_id": "theme_touhou_example",
  "version": "1.0.0",
  "content_types": ["text", "sprites", "audio"],
  "required_game_version": ">=0.1.0",
  "license_file": "LICENSE.md"
}
```

## 东方主题风险

东方主题需要处理二创规则和商业权益风险。官方基础包不内置东方官方素材。Workshop 中涉及东方的 Mod 必须提供来源说明，并保留下架和禁用机制。

## 加载顺序

1. 基础主题。
2. 官方可选主题。
3. Workshop 主题。
4. 用户本地覆盖。

缺失资源回退到基础主题。
