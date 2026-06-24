# 在线对局 Replay

## 服务端保存内容

- match_id。
- ruleset_version。
- server_seed。
- player_ids。
- deck_snapshots。
- input_streams。
- card_events。
- major_state_hashes。
- final_result。

## 下载与播放

- 玩家可在战绩中下载自己的对局 Replay。
- 排行榜高分对局可公开 Replay。
- 争议对局由服务端 Replay 复核。

## 权威性

线上 Replay 不采信客户端本地模拟结果。客户端只负责播放服务端记录。

## 隐私

- Replay 中不记录聊天私信。
- 可隐藏对手完整账号标识。
- 卡组快照在公开模式中按赛季规则决定是否展示。公开展示时使用观看者当前主题的 i18n 文本，不把主题文本写入 Replay。

## 版本兼容

- Replay 绑定 ruleset_version。
- 若客户端版本不支持旧规则，提示需要兼容播放器或无法播放。
- 服务端可保留关键赛季的回放校验逻辑。
