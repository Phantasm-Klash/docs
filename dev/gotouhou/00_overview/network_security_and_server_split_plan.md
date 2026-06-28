# 网络安全与服务端拆分调整计划

状态更新时间：2026-06-27

## 调整结论

服务端从“单一 Nakama/Go 服务同时承载业务和高频战斗”调整为“Nakama + Go Runtime 业务后端 + C++ 战斗后端 + 共享协议/规则仓库”的多服务结构。Nakama 不取缔，继续作为业务服务器核心：

- 业务网络层：账号、登录授权、资料、饰品、道具、背包、卡组、宝箱、活动、排行榜、匹配、模式选择、房间和用户交互走 Nakama HTTPS RPC + Nakama WSS。TLS 1.3 是传输安全底线，在高价值业务包上叠加应用层 ECC 会话加密、包签名、序号、时间戳和重放保护。
- 游戏网络层：弹幕竞技、PVP、大逃杀、世界 Boss、副本 Boss 等强实时对局走 ECDHE + KCP/UDP + protobuf + ChaCha20-Poly1305。C++ 战斗服务端保持服务器权威模拟，客户端只发送输入和请求意图。
- Nakama + Go Runtime 业务后端：负责账号、会话、授权、Steam 闭源适配入口、用户资料、库存、饰品/道具/卡组、匹配、房间、模式资格、战斗票据、结算入库、活动、排行榜、业务 WSS 和社交交互。
- C++ 战斗后端：负责 PVP 和 Boss 战的 tick 推进、弹幕、碰撞、擦弹、卡牌生效、模式机制、快照、事件、Replay 输入流和战斗结果。
- Steam 对接、商品、官方商业库存、市场交易、商业服风控和运营敏感配置闭源。开源版保留用户注册、登录、资料管理、基础库存、卡组、模式选择、房间/匹配和基础战斗服务。

## 协议分层

### 业务层：HTTPS + WSS + 应用层安全 envelope

业务层负责低频但高价值的数据。默认协议：

- Nakama HTTPS RPC：登录、注册、资料、背包、饰品、道具、卡组、宝箱、奖励、活动、排行榜、模式配置、战斗票据申请。
- Nakama WSS：在线状态、聊天或轻社交、房间状态、匹配进度、邀请、活动通知、战斗服务器分配、结果通知。它不再承载高频弹幕战斗 tick。
- TLS：强制 TLS 1.3；开发环境可使用本地证书，生产环境使用正式证书和 HSTS。
- 应用层加密：对登录后业务包使用 X25519 ECDH/ECDHE 派生会话密钥，HKDF-SHA256 或 BLAKE3 KDF 派生 `client_to_server`、`server_to_client`、`signing` 子密钥。
- 包签名/认证：每个业务包包含 `session_id`、`seq`、`timestamp_ms`、`nonce`、`op_code`、`body_ciphertext` 和 `auth_tag`。普通业务包使用 AEAD tag + session MAC；高价值变更包可额外使用 Ed25519/ECDSA 签名。服务端下发配置、战斗票据和结算回执必须由服务端 Ed25519 签名。
- AEAD 算法：优先 ChaCha20-Poly1305；在 x86 服务器且 AES-NI 明确可用时可选 AES-256-GCM。算法、key id 和协议版本写入 envelope，便于轮换。

注意：业务层已有 TLS，不应把自定义 ECC 当成替代 TLS。应用层 envelope 的目的，是给高价值业务操作增加请求绑定、防重放、防串改、跨代理审计和离线签名校验能力。

### 游戏层：ECDHE + KCP + protobuf + ChaCha20-Poly1305

游戏层负责高频实时状态。默认协议：

- UDP + KCP：KCP 用于可靠有序输入、卡牌请求、模式动作、关键事件和必要快照。后续可增加原始 UDP 冗余快照或 FEC，但 v0.1 先只引入 KCP，降低复杂度。
- protobuf：所有战斗包使用 protobuf schema 生成 Go、C++ 和客户端绑定。消息必须带 `protocol_version`、`ruleset_version`、`match_id`、`player_id`、`tick`、`seq`、`ack` 和 `payload_type`。
- 握手：客户端先向 Nakama/Go 业务服务申请 `battle_ticket`。票据包含 `match_id`、`user_id`、`deck_snapshot_hash`、`ruleset_version`、`mode_id`、`battle_server_id`、`endpoint`、`expires_at` 和一次性 nonce，并由业务服务端 Ed25519 签名。C++ 战斗服务端验证票据后，与客户端执行 X25519 ECDHE，使用 HKDF 派生战斗会话密钥。
- 加密：KCP payload 加密使用 ChaCha20-Poly1305 或 XChaCha20-Poly1305。nonce 由方向位、连接 id、递增包序号和随机 salt 组合，禁止重复。
- 重放保护：战斗服务端维护滑动窗口，拒绝过期 tick、重复 seq、过期 ticket、重复 ticket 和异常快进输入。
- 服务端权威：客户端不能提交位置、伤害、命中、擦弹、奖励、Boss 扣血、排名或结算结果，只能提交输入、卡牌槽位请求、ready、reconnect 和模式动作意图。

### 服务间通信

Nakama/Go 业务服务与 C++ 战斗服务之间使用内网 gRPC/protobuf 或 HTTP/2/protobuf：

- 传输层使用 mTLS。
- Nakama/Go 服务创建业务 match allocation，签发 battle ticket，并把模式配置、玩家快照、卡组快照、规则版本和 server seed 下发给 C++ 战斗服务。
- C++ 战斗服务周期性上报 match 状态摘要、异常审计、Replay 输入流摘要，结算时提交 `battle_result`。
- Nakama/Go 服务验证 `battle_result` 的服务端签名、match id、ruleset version、玩家列表、幂等键和结果哈希，再写入 PostgreSQL/Nakama storage 并发放奖励。
- C++ 战斗服务不得直接发放资产、修改库存、写官方商业库存或调用 Steam API。

## 服务职责拆分

| 模块 | 语言/仓库 | 开源性 | 职责 |
| --- | --- | --- | --- |
| SpellKard client | Godot/GDScript + 可选 GDExtension | 开源 | UI、输入、练习、本地展示、业务 HTTPS/WSS 客户端、战斗 KCP 客户端、Replay 展示、主题和可访问性。 |
| Gensoulkyo business | Nakama + Go Runtime | 开源核心 | 注册登录、session、资料、库存、饰品、道具、卡组、宝箱、活动、排行榜、匹配、房间、模式选择、业务 WSS、战斗票据、结算入库、基础后台。 |
| Battle server | C++ | 开源核心 | PVP、Boss、大逃杀等实时战斗权威模拟，KCP 会话、protobuf 快照、Replay 输入流、战斗审计和结果签名。 |
| Shared protocol/rules | protobuf + JSON/YAML/TOML + codegen | 开源 | protobuf schema、错误码、ruleset schema、卡牌/弹幕/机体/模式配置、签名票据结构和代码生成脚本。 |
| Steam adapter | Go/C++/平台 SDK | 闭源 | Steam 登录、App 所有权、Steam Inventory、Workshop、成就、市场交易、商业库存映射和官方商品。 |
| Commercial ops | Go + SQL + private config | 闭源 | 官方商品、掉落频率、风控、封禁联动、运营后台敏感配置、私有部署密钥。 |

## 开源与闭源仓库规划

建议仓库拆分：

- `docs`：开源。规划、接口边界、公开文档、网站。
- `SpellKard`：开源。Godot 客户端、业务网络适配、战斗网络客户端接口、本地练习和 UI。若 KCP/crypto/protobuf 用 GDExtension，可放在本仓库 `native/` 或独立开源仓库。
- `Gensoulkyo`：开源。Nakama + Go Runtime 业务后端核心，包含注册登录、session、资料、基础库存、卡组、开源宝箱、匹配、房间、模式选择、业务 WSS、战斗票据、结算接收和基础运维接口。当前标准库 HTTP MVP 保留为迁移前的契约测试和开发 fallback。
- `PhK-Protocol`：开源。protobuf schema、业务 envelope schema、错误码、服务间协议、ruleset schema、代码生成脚本、兼容性测试夹具。
- `PhK-BattleServer`：开源。C++ 战斗服务端、KCP/UDP 网络层、战斗模拟、Boss/PVP 模式、Replay 战斗记录、性能测试。
- `PhK-SteamAdapter`：闭源。Steamworks SDK、Steam Web API、Steam Inventory、Workshop、成就、所有权校验。
- `PhK-CommerceOps`：闭源。官方商品、商业库存策略、掉落概率、市场属性、风控、封禁、私有后台和运营敏感配置。
- `PhK-OfficialDeploy`：闭源或私有。官方环境 IaC、证书、密钥、服务编排、监控告警和发布策略。开源版只保留 sanitized compose/k8s 示例。

## 需要调整、移植和重构的内容

### SpellKard 客户端

- 将现有 Gensoulkyo HTTP 适配保留为业务层，不再承担高频战斗输入、快照和事件传输。
- 新增业务 HTTPS/WSS secure envelope：请求序号、时间戳、nonce、AEAD、session MAC/sign、错误码和重放处理。
- 新增战斗网络模块：KCP/UDP、protobuf 编解码、ECDHE 握手、ChaCha20-Poly1305 加解密、重连、tick/seq/ack、快照投射。
- 建议把战斗网络热路径做成 GDExtension/C++ 或 C# 原生模块，GDScript 只消费已解密/解码后的模型事件。
- `network_match_model.gd` 需要从 HTTP snapshot/event projection 拆成业务状态投射和战斗状态投射。
- Replay 模型需要接受 C++ 战斗服务签名的输入流摘要、规则版本和结果哈希。

### Gensoulkyo Nakama/Go 业务后端

- 保留当前 HTTP MVP 中的账号、bootstrap、库存、卡组、宝箱、奖励、活动、排行榜、匹配、房间和结果幂等逻辑。
- 将这些业务逻辑迁移或适配到 Nakama RPC、storage、matchmaker、status/socket 和 Go Runtime 模块；标准库 HTTP MVP 保留为契约测试、离线开发和迁移对照。
- 移除或降级 Nakama/Go 内部高频战斗模拟，把它保留为测试 fixture 或本地单进程 fallback。
- 新增 battle ticket 签发、battle server 发现、match 分配、战斗服务注册、战斗结果验签和服务间审计。
- 使用 Nakama WSS/status/socket 承载业务通道：房间、匹配、好友/邀请、活动通知、战斗服务器分配和结算通知。
- PostgreSQL schema 需要增加 `battle_servers`、`battle_tickets`、`match_allocations`、`battle_result_audits`、`packet_key_versions` 和服务端签名 key id。
- Steam 相关登录、商品、官方库存和市场接口只保留开源抽象，不放真实 SDK、key、掉落策略和商品配置。

### C++ 战斗服务端

- 新建 C++ 服务：KCP listener、ticket verifier、ECDHE handshake、protobuf dispatcher、authoritative tick loop、snapshot/event encoder、Replay stream builder、result signer。
- 从现有 Go/SpellKard 原型迁移弹幕数学、卡牌效果、机体参数、Boss/PVP 模式逻辑，迁移过程中以 `PhK-Protocol` 的规则配置和 golden replay 为准。
- 支持水平扩容：战斗服务无资产状态，match 结束后把结果回传 Go；崩溃恢复依赖 Go 重新分配、Replay 输入流和 match state checkpoint。
- 需要性能测试：tick 时间、玩家数、Boss 战弹幕量、KCP 包量、加密耗时、protobuf 编码耗时、快照大小。

### 共享协议和配置

- 所有消息、票据、错误码、版本字段进入 `PhK-Protocol`。
- protobuf schema 需要分包：`business.proto`、`matchmaking.proto`、`battle.proto`、`replay.proto`、`admin.proto`。
- 规则配置需要带 `ruleset_version` 和 hash。Go、C++、Godot 三端都只接受相同版本。
- 为关键协议建立 golden fixtures：一组输入、seed、卡组、模式配置，应在 C++ 服务和客户端回放展示中得到相同结果哈希。

## 多仓库编译打包方案

### 构建顺序

1. `PhK-Protocol`
   - 运行 protobuf/ruleset codegen。
   - 产出 Go package、C++ headers/sources、Godot/GDExtension 绑定或 JSON descriptor、schema 文档和 golden fixtures。
   - 产物以 git tag、语义版本和 artifact checksum 发布。
2. `Gensoulkyo`
   - 拉取指定 `PhK-Protocol` tag。
   - 运行 Nakama Go Runtime tests、HTTP fallback tests、PostgreSQL migration tests、业务 envelope tests、battle ticket tests。
   - 打包 `gensoulkyo-business` Nakama runtime artifact、可选 HTTP fallback image 和 CLI migration artifact。
3. `PhK-BattleServer`
   - 拉取同一 `PhK-Protocol` tag。
   - 使用 CMake + vcpkg/Conan 或固定 third_party lock 构建。
   - 运行 battle simulation tests、KCP crypto tests、golden replay tests、性能基准。
   - 打包 `phk-battle-server` Docker image、符号文件和性能报告。
4. `SpellKard`
   - 拉取同一 `PhK-Protocol` tag。
   - 构建 Godot 客户端和可选 native networking module。
   - 运行 Godot headless smoke、业务协议投射、战斗 protobuf fixture、Replay 展示和资产授权检查。
5. 闭源仓库
   - `PhK-SteamAdapter` 和 `PhK-CommerceOps` 在私有 CI 中引用公开 artifact checksum。
   - 私有 CI 额外运行 Steam ticket、Inventory、商品、市场、风控和官方部署测试。

### 版本兼容

- 客户端、Go 业务端和 C++ 战斗端必须记录 `protocol_version`、`ruleset_version`、`business_api_version` 和 `battle_api_version`。
- 匹配前由 Go 服务检查客户端版本是否允许进入对应模式。
- 战斗票据绑定版本、卡组快照 hash、mode config hash 和 battle server build id。
- 不允许战斗中热更新规则；只允许新 match 使用新规则。

### 开源自托管包

开源 release 至少包含：

- `gensoulkyo-business` Nakama runtime image/artifact。
- 可选 `gensoulkyo-http-fallback` 开发镜像。
- `phk-battle-server` Docker image。
- PostgreSQL migrations。
- sanitized `docker-compose.yml` 或 k8s 示例。
- `PhK-Protocol` schema 和 codegen artifact。
- SpellKard 客户端构建说明。
- 本地自签 TLS/测试 key 生成脚本，生产环境必须替换。

闭源官方包额外包含 Steam adapter、商业商品配置、官方证书、密钥、风控和部署策略，不进入开源 release。

## 安全与性能验收

- 业务层所有写操作必须有 seq、timestamp、nonce、幂等键和服务端审计记录。
- 战斗层在 30/80/150/250ms、丢包和抖动条件下验证输入延迟、快照修正、重连和 Replay 结果。
- 包加密不能复用 nonce；服务端必须拒绝重复 seq 和过期 ticket。
- 服务端签名 key 支持 key id、轮换、过期和回滚。
- C++ 战斗服务在目标玩家数和 Boss 弹幕密度下，单 tick 计算、protobuf 编码和加密发送都必须低于预算。
- 任何客户端提交的资产、奖励、伤害、Boss 扣血、排名或结算结果都必须被拒绝。

## 近期落地顺序

1. 新建 `PhK-Protocol` 规划和 schema 草案，先覆盖业务 envelope、battle ticket、battle input、snapshot、event、result。当前已落地独立 `D:\gotouhou\PhK-Protocol` 骨架，包含 `common/business/matchmaking/battle/replay/admin.proto`、ruleset JSON schema、最小 v0.1 flow fixture、codegen 计划和 `tools/check_protocol.py` 协议检查。Gensoulkyo 已消费 dependency-light Go manifest，PhK-BattleServer 已消费 dependency-light C++ manifest，SpellKard 已消费 JSON descriptor 做迁移期契约检查；下一步是冻结 v0.1 字段并把临时 manifest/descriptor 桥替换为完整 Go/C++/Godot protobuf 生成。
2. 在 Gensoulkyo 中保留当前 HTTP 输入/快照作为过渡测试接口，同时先落地 battle server register/list/heartbeat、match allocation、短期 Ed25519 battle ticket、HTTP fallback 契约测试和业务 envelope 兼容 guard。当前已完成标准库 Go 骨架、单元/HTTP 测试、battle ticket fallback，以及 `runtime/security` 中可被 HTTP、未来 Nakama RPC 和业务 WSS 共用的业务 envelope request adapter + guard：HTTP header、Nakama RPC-style payload 和 Nakama WSS-style payload 现在都能构造成同一个 `BusinessEnvelopeRequest`，并共享同一套 replay guard。`runtime/nakamaapi` 已新增 SDK-neutral Nakama Runtime adapter skeleton，可把外部 Nakama user/session 映射进 core session，分发登录、bootstrap、库存、卡组、宝箱、心跳、匹配、房间、活动、战斗分配/票据等业务 RPC，以及 presence/matchmaking/room 业务 WSS-style 消息；登录外的 authenticated 调用会要求 business envelope，并把缺失、非法或重放的 envelope 记入同一个审计 guard。`cmd/gensoulkyo_nakama` 已新增 `nakama` build-tagged SDK 绑定源码，用于注册 RPC 并把 Nakama context/payload 转交给 `runtime/nakamaapi`；当前环境未能拉取 `github.com/heroiclabs/nakama-common/runtime`，因此真实 `go test -tags nakama`/plugin 构建仍需在联网或缓存 SDK 的 CI 中验证。带 envelope 的请求会检查版本、seq、timestamp、nonce、op、key id、mode 和 64 位 hex tag，并拒绝重复 seq/nonce 与过期/未来时间戳；未带 envelope 的 HTTP 请求仍保留旧 HTTP fallback 兼容。HTTP 已通过该 adapter 接入 guard，并提供开发期状态端点暴露 accepted/rejected/audit 摘要。guard 已有 audit sink 接口和标准库 `database/sql` envelope audit writer；`migrations/001_business_security_audit.*.sql` 已定义 envelope key、audit、nonce window、battle ticket audit 和 match allocation audit 的 PostgreSQL 草案；`runtime/storage` 与 `cmd/gensoulkyo -migrate-up` 已提供显式启用的 `.up.sql` migration runner；开源 Postgres driver 策略已选用 pgx stdlib（当前 pin 到兼容 Go 1.20 的 v5.5.5）。下一步是在 CI/服务器环境完成 Nakama SDK tag 构建，并把 audit sink 接到真实 PostgreSQL 连接。
3. SpellKard 保留 HTTP live check，已能投射 Gensoulkyo battle allocation/signed ticket 到 matchmaking/network 模型，并已新增 battle result submit 回执的只读状态投影，用于显示 C++ 战斗服结果回传后由 Nakama/Go 验证、幂等和入库的状态；该投影不让玩家客户端成为结算权威。Network Match 网络安全状态面板用于区分业务 HTTPS/WSS/ECC/sign 目标、战斗 ECDHE/KCP/protobuf/ChaCha20-Poly1305 目标，以及 C++ result -> Nakama/Go callback 状态。当前 authenticated HTTP fallback 请求会构造业务 envelope 脚手架并发送 `X-PhK-Business-*` 头，包含 seq、timestamp、nonce、op、key id、tag 和 mode，以对接服务端迁移期 replay guard。客户端体验侧已把 debug 壳继续收敛为玩家入口：首页保持 Play、Collection、Community、Player Settings 四个主按钮和大 portrait/standee 区，旧 dashboard 卡片入口保持隐藏；考证/匹配下沉到 Play，卡组/宝箱/Replay/Workshop 下沉到 Collection，活动/好友/社交/推广下沉到 Community，手柄曲线/按键/音量/画面分辨率下沉到 Player Settings。二级/三级页面复用 row metadata 渲染分类、状态卡、焦点面板、概览卡、快捷操作、设置控件，并新增父级/首页快速导航与 `ui_cancel` 返回层级。`UIScreenModel.page_layout()` 现在作为正式 Godot UI 迁移契约，区分 home lobby、hub、settings、community、matchmaking、network room、practice playfield、running battle room、collection 和 mode-select：匹配/网络房间不再运行本地弹幕 demo，练习页才推进本地 playfield，running network battle 只绘制服务端投影而不推进本地 practice tick。下一步新增真实业务 HTTPS/WSS secure envelope 状态机、protobuf descriptor 消费和 KCP battle client GDExtension/C++ 骨架，同时把这些程序化菜单迁移为最终 Godot Control 场景。
4. `PhK-BattleServer` C++ battle server skeleton 已落地，当前包含 ticket/handshake/KCP endpoint/protocol dispatcher/server facade/CLI/CTest/checker，并能通过本地 CMake/MSVC 构建测试。下一步把结构占位依次替换为真实 protobuf C++ 绑定、Ed25519 ticket 验签、X25519 ECDHE/HKDF/transcript 签名、KCP event loop、ChaCha20-Poly1305 包加密和 Go/Nakama 回调。
5. 将最小 1v1 弹幕 tick 从 Go/客户端原型迁移到 C++，用 golden replay 锁定结果；Go HTTP 内部模拟降级为 fixture/fallback。
6. 扩展到 Boss 战和大逃杀；最终让 Nakama/Go 只负责业务、会话、匹配、房间、通知和结算入库，C++ 负责所有强实时战斗。

## 2026-06-27 实现同步

- `PhK-Protocol`：v0.1 draft schemas、ruleset schema、fixture、codegen notes、`descriptors/phk_v1_descriptor.json`、`gen/go/phk/v1/manifest.go`、`gen/cpp/phk/v1/manifest.hpp` 和 `tools/check_protocol.py` 已存在并通过检查。JSON descriptor、dependency-light Go manifest 与 dependency-light C++ manifest 是生成完整 Go/C++/Godot protobuf 绑定前的临时跨仓库契约桥。
- `Gensoulkyo`：Go HTTP fallback MVP 已覆盖登录/bootstrap/库存/卡组/宝箱/匹配/房间/模式动作、battle server allocation 和 signed battle ticket 契约。`runtime/security` 现已提供可复用业务 envelope request adapter/兼容 guard，可从 HTTP header、Nakama RPC-style payload 和 Nakama WSS-style payload 构造同一个 `BusinessEnvelopeRequest`，并在客户端发送 `X-PhK-Business-*` 头时做版本、seq/timestamp/nonce/tag 检查、重放拒绝、脱敏审计快照和 audit sink 输出；HTTP fallback 已接入该 adapter。`runtime/nakamaapi` 现已提供 SDK-neutral RPC/WSS-style handler skeleton，用同一 guard 保护 authenticated business calls，并能映射外部 Nakama user/session。`cmd/gensoulkyo_nakama` 已有 `nakama` build-tagged SDK 绑定源码，但真实 tag 构建仍待可拉取 Nakama SDK 的环境验证。Gensoulkyo 已通过本地 replace 消费 PhK-Protocol Go manifest，服务端 protocol/business/battle/ruleset version 常量和关键 message field gate 已由协议仓驱动；完整 protobuf Go 绑定仍待替换当前手写结构。首个 PostgreSQL 安全审计迁移草案、`database/sql` envelope audit writer、显式 migration runner 和 pgx stdlib driver 注册已存在，但 repository wiring 和真实 X25519/AEAD/sign envelope 仍待迁移实现。
- `SpellKard`：Godot 客户端仍以 HTTP fallback adapter 做 live check，但 Network Match 页已暴露业务层 `HTTPS + WSS + ECC seal + sign`、战斗层 `ECDHE + KCP/UDP + protobuf + ChaCha20-Poly1305` 和 C++ result -> Nakama/Go callback 的状态行，并加载共享 descriptor 做最小契约验证。客户端现在能构造 battle result submit fallback 请求并应用 server-authoritative 回执到 API/network 状态模型，记录 accepted/rejected、settlement key、duplicate、result hash、replay id 和 key id，用于联调观察，不能作为玩家客户端权威结算入口。authenticated Gensoulkyo 请求现在会携带带 timestamp 的业务 envelope 脚手架头，用于对齐服务端 replay guard。客户端本地 deck/replay/smoke fixture 默认 ruleset 已对齐共享 `ruleset-local-s0`。客户端 UX 已继续从 debug 状态推进：home 隐藏 gameplay/HUD、暂停本地 demo tick、展示只含 Play、Collection、Community、Player Settings 四个主入口的 lobby 与大 portrait 区；旧 dashboard 卡片不再作为首页入口；考证、匹配、卡组、宝箱、Replay、活动通告、好友、社交媒体、推广链接和设置细节等 deeper surfaces 下沉到二级/三级页面的状态卡、hub row、分类 tab、焦点动作、概览卡、快捷操作和设置控件中，并保留父级/首页导航和返回层级。新增的 `page_layout()` 契约已让测试可验证 hub/collection/settings/community/matchmaking/network-room/playfield/battle-room 的显示策略，避免匹配菜单和网络准备房间继续表现成弹幕 debug 画面。这是客户端体验、架构状态投射和迁移期合同检查，不代表生产加密已经完成。
- `PhK-BattleServer`：C++17 CMake 骨架已建立并通过 `python tools\check_battle_server.py --build`，checker 也会验证共享 descriptor 与 generated C++ manifest 中的关键 battle message/field，默认 ruleset/version 常量已从 `PhK-Protocol/gen/cpp/phk/v1/manifest.hpp` 消费并对齐共享 `ruleset-local-s0`。当前 crypto/KCP/protobuf 行为是结构占位，只用于边界和测试先行。
- 近期优先级：继续冻结协议/codegen，把当前 Go/C++ manifest 与 JSON descriptor 桥升级为完整 protobuf Go/C++/Godot 生成；在联网/CI 环境验证 `cmd/gensoulkyo_nakama` 的真实 Nakama SDK tag 构建、接入真实 PostgreSQL audit sink；再接真实 Ed25519/X25519/KCP/AEAD；最后迁移最小 1v1 authoritative tick 和结果签名回调。
