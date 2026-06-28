# 确定性帧同步技术复盘

状态更新时间：2026-06-28

## 资料说明

本次复盘尝试读取 `https://share.gemini.google/kC6I3sKB9ivH`，当前环境只能跳转到 Gemini share 页面，无法取得可引用正文。因此以下结论基于本仓库现有实现、既有规划文档和确定性帧同步的通用工程路线。若后续补充 Gemini 原文，需要再做一次逐条对照。

## 技术路线结论

本项目不应采用纯 P2P lockstep。弹幕、擦弹、卡牌效果、Boss 血量、奖励和排名都涉及公平性与经济结算，生产路线应定义为：

- C++ Battle Server 做服务器权威固定 tick 模拟。
- 客户端只上传输入和模式动作意图，本地只做移动预测、表现预演和快照修正。
- 战斗服保存输入流、关键事件、规则版本、种子、卡组快照 hash 和 state hash，用于 Replay 与争议复核。
- Nakama/Go 业务服只负责账号、匹配、房间、battle ticket、结算验签、资产入库和业务通知，不承载生产高频 tick。

也就是说，本项目的“确定性帧同步”是服务器权威的输入同步 + 固定 tick + 可复现模拟 + 快照校验，不是让所有客户端共同决定权威状态。

## 当前实现能力

### 客户端 SpellKard

- `NetworkMatchModel` 已有输入延迟 2-4 tick、预测修正阈值、快照/事件/重连/结果投射、非法客户端字段列表和 battle allocation/ticket 状态。
- `BattleNetworkClientModel` 已有 KCP/UDP、X25519 ECDHE、protobuf、ChaCha20-Poly1305 的状态机脚手架，能从 battle ticket 生成握手准备状态和 packet header。
- `InputCodec` 已把方向压缩为 bitmask，并将 slow、shoot、bomb、card_slot 作为输入意图。
- `ReplayRecorder` 已记录 ruleset、seed、input stream、event stream 和 hash，但目前主要服务本地 replay。
- 当前客户端尚未具备真实 KCP、真实 protobuf 编解码、真实 ECDHE/HKDF、真实 AEAD、native battle client binding 和权威快照驱动的完整重模拟。

### 业务服 Gensoulkyo

- Go HTTP MVP 已实现登录、bootstrap、匹配/房间、ready/input/snapshot/events、断线重连、结算、rematch、replay audit、battle server allocation、signed battle ticket 和 signed battle result submit fallback。
- `SubmitInput` 已拒绝客户端提交分数、位置、伤害、奖励、Boss HP、手牌等权威字段，输入 tick/seq 必须单调。
- `snapshotLocked` 已下发玩家、弹幕 delta、分数、active_cards、mode_state、events 和 state_hash。
- 当前 `TickRate = 60`，而早期规划写的是 30 tick/s；后续必须以协议和 ruleset 明确锁定一个值。
- 当前模拟仍使用 Go `float64`、JSON snapshot hash 和内存状态，适合作为契约 MVP，不适合作为跨语言确定性基准。

### 共享协议 PhK-Protocol

- 已有 `BusinessSecureEnvelope`、`BattleTicket`、`SignedBattleTicket`、`BattlePacketHeader`、`BattleInput`、`BattleSnapshot`、`BattleEvent`、`BattleResult` 和 `SignedBattleResult` proto 草案。
- 战斗快照已经使用 `x_milli/y_milli/vx_milli/vy_milli/radius_milli`，方向正确：协议层应优先定点整数，不把浮点作为跨端权威数据。
- 当前仍是 draft schema + manifest/descriptor 桥，尚未替换为完整 Go/C++/Godot protobuf 生成物和 golden fixture。

### C++ Battle Server

- 已有 ticket、handshake、KCP endpoint、protocol dispatcher、server facade、result boundary 和 CTest/checker 骨架。
- Dispatcher 已做版本、match/player identity、seq replay、tick jump 和禁止客户端 result 的结构检查。
- 当前 crypto、KCP、protobuf 和 authoritative simulation 都是结构占位，尚未具备真实同步能力。

## 必须修正的规划口径

### tick 率

v0.1 建议统一锁定 60Hz 逻辑 tick：

- 现有 Go 业务服已经是 60Hz。
- 本地 STG 手感、低速移动、擦弹窗口和 deathbomb 窗口更容易与 60 FPS 渲染对齐。
- 2-4 tick 输入延迟在 60Hz 下约 33-67ms；若使用 30Hz 则变成 67-133ms，手感风险更高。

如果性能或带宽实测不足，可以在新 ruleset 中降到 30Hz，但不能让同一协议版本内同时存在 30Hz/60Hz 混跑。

### 确定性数值

C++ 迁移时需要把战斗核心从浮点原型收敛为定点整数：

- 位置、速度、半径：使用 milli 单位或 Q 格式整数。
- 角度：使用固定查表、整数角度单位或只在服务端生成后落成整数速度。
- RNG：只接受 match seed、tick、pattern id、spawn index、card event id，不接受系统时间和容器迭代顺序。
- 容器遍历：所有玩家、子弹、事件、卡牌状态按稳定 id 排序。
- state_hash：使用 canonical binary/state digest，不使用语言相关 JSON 序列化作为长期标准。

### 输入窗口

输入协议需要同时记录：

- `input_tick`：该输入要作用的权威 tick。
- `seq`：连接内严格递增包序号。
- `ack`：客户端确认收到的服务端包序号或 snapshot tick。
- `send_client_tick` 可作为调试字段，不参与权威模拟。

战斗服按 `input_tick` 入缓冲。早到输入缓存；迟到输入按规则使用上一 tick 或中立输入，并把 fallback 记录进 Replay。客户端不应提交“当前位置”来补偿延迟。

### 快照与 hash

v0.1 推荐：

- 战斗服 60Hz 模拟。
- 正常快照每 2-4 tick 下发一次，即 15-30 snapshot/s。
- 关键事件立即发 event；重连和 hash mismatch 发 full snapshot。
- 高频弹幕优先同步 spawn/despawn/关键变速事件和摘要，客户端用相同规则重建表现。
- state_hash 至少覆盖 tick、玩家定点位置、生命/无敌、资源、分数、子弹摘要、active card、RNG 状态和模式状态摘要。

### 交互协议边界

客户端允许：

- battle handshake。
- ready / reconnect / ping。
- input：direction_bits、slow、shoot、bomb、card_slot。
- mode action intention：例如大逃杀选卡、Boss 卡牌让渡请求。
- business request：登录、bootstrap、背包、卡组、匹配、房间、battle ticket 请求等。

客户端禁止：

- 位置、命中、擦弹、伤害、分数、Boss HP、排名、奖励、掉落、开箱结果、结算结果。
- 伪造 active_cards、hand、energy 或服务端种子。
- 提交 `BattleResult`。结果只能由 C++ Battle Server 签名后回传 Nakama/Go。

## 迁移验收顺序

1. 冻结 PhK-Protocol v0.1：tick rate、定点单位、输入字段、snapshot/event/result、business envelope、battle ticket、错误码和版本兼容策略。
2. 建立 golden replay fixture：同一 seed、ruleset、deck snapshot、输入流，在 C++ 模拟和客户端 replay 展示中得到相同关键 state hash。
3. 将 Go HTTP match 模拟降级为 contract/fallback，只保留接口测试价值，不再作为生产确定性基准。
4. 在 C++ 实现最小 1v1 tick：输入缓冲、移动、射击、弹幕 spawn/move/despawn、碰撞、擦弹、Bomb、卡牌槽位请求和 snapshot/event。
5. 接入真实网络：ticket 验签、X25519 ECDHE/HKDF、KCP、protobuf、ChaCha20-Poly1305、seq/nonce/replay guard。
6. 接入结果闭环：C++ 生成 signed battle result，Nakama/Go 验签、幂等、入库、发奖和通知。
7. 跑延迟矩阵：30/80/150/250ms、丢包、抖动、断线重连、快照修正、Replay 复现和异常审计。

## 当前风险

- tick 率文档与实现不一致，必须立即统一。
- Go MVP 的浮点和 JSON hash 不能直接作为跨语言确定性标准。
- BattleNetworkClientModel 和 PhK-BattleServer 目前是协议/状态脚手架，不代表真实同步已经完成。
- protobuf 仍未成为三端唯一数据结构，manifest/descriptor 桥只能作为过渡。
- 客户端重模拟策略已有规划，但缺少从 full snapshot + input buffer 到当前 tick 的真实实现和测试。
