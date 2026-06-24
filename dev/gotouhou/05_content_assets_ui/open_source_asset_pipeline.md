# 开源素材管线

## 来源

优先使用：

- OpenGameArt。
- Kenney。
- itch.io 中明确可商用素材。
- 自制素材。
- 委托且合同明确授权的素材。
- Steam Workshop 中用户上传且通过审核的主题素材。

## 导入流程

1. 下载原始素材。
2. 记录来源、作者、协议和日期。
3. 放入 `assets/raw/`。
4. 转换尺寸、格式和命名。
5. 放入 `themes/base/` 或对应主题目录。
6. 更新 license manifest。

## 命名

建议格式：

- `bullet_round_blue_01.png`。
- `player_focus_balanced_01.png`。
- `ui_icon_bomb_01.png`。

## 禁止

- 未授权同人图。
- 东方官方截图裁切。
- 未授权音乐 remix。
- 来源丢失的素材包。
基础发行包还禁止内置东方官方或未经授权同人素材。

## 验收

任何进入构建包的素材，都能在 license manifest 中找到来源和协议。

## 主题包

主题包必须包含 manifest：

```json
{
  "theme_id": "example_theme",
  "display_name_key": "theme.example.name",
  "version": "1.0.0",
  "asset_license": "see LICENSE.md",
  "replaces": ["text", "sprites", "audio"]
}
```

主题包只替换表现资源，不改变玩法数据。
