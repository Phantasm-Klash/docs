# 02 Networked Match

本阶段把本地 STG 核心迁移到联机 PVP。核心原则是服务器权威：客户端只上传输入和出牌意图，服务器结算真实状态。

## 目标

- 1v1 权威房间。
- 固定 tick 模拟。
- 输入同步和延迟补偿。
- 服务器快照修正。
- 断线重连。
- 在线 Replay。
- 反作弊基础规则。

## 初版网络模型

- 客户端 60 FPS 渲染。
- v0.1 锁定服务端 60 tick/s 模拟；若后续实测需要 30 tick/s，必须通过新的 ruleset/protocol 版本切换，禁止同一对局混用 tick 率。
- 客户端每 tick 或合并多个 tick 上传输入。
- 服务端每 2-4 tick 下发状态快照，即约 15-30 snapshot/s。
- 客户端本地预测移动，收到权威快照后平滑修正。
- 卡牌施放使用稳定 card_code 和 i18n key，东方主题只替换显示文本。
- 所有模式通过 `mode_id` 和 `mode_ruleset_version` 进入同一服务器权威框架，具体逻辑由模式 handler 实现。
- 生产路线为服务器权威确定性帧同步：C++ Battle Server 固定 tick 推进，客户端只提交输入和模式动作意图，Nakama/Go 只负责业务、匹配、票据和结算验签。

## 复盘结论

详见 `deterministic_lockstep_review.md`。当前 Go HTTP match MVP 和 Godot battle client 都已经具备协议/状态脚手架，但还不是完整生产同步链路。进入 C++ Battle Server 迁移前，必须先统一 tick 率、定点单位、输入窗口、state hash 和 golden replay 验收。
