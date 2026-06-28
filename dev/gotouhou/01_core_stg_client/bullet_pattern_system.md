# 弹幕模式系统

## 目标

弹幕系统需要同时支持单机练习、PVP 权威模拟、Replay 复现和卡牌修改。所有模式都应以配置数据驱动。

## 基础弹型

- 固定弹：按 tick 和参数生成。
- 随机弹：使用确定性 RNG 和服务端 seed。
- 自机狙：生成时读取目标玩家位置。
- n-way：扇形多方向发射。
- 环形弹：按角度均分生成。
- 弹链：子弹在指定 tick 分裂或变速。
- 开花弹：移动一段时间后爆开。
- 诱导弹：缓慢转向目标，需限制最大转向角。

## 阶段变化

- 普通阶段：低密度，帮助玩家建立节奏。
- 压力阶段：提高速度、密度或自机狙比例。
- 发狂阶段：对局后半或终幕卡牌触发，高风险高收益。

## 卡牌改写接口

卡牌不得直接改写底层弹体数组，而应通过 modifier 影响生成参数：

- speed_multiplier。
- density_multiplier。
- angle_offset。
- curve_strength。
- aim_bias。
- graze_score_multiplier。

## 确定性要求

- 任何随机结果必须能由 seed、tick、pattern_id、spawn_index 重建。
- 不能使用客户端当前帧率、系统时间或非确定性浮点随机。
- 线上 Replay 以服务端生成记录为准。

## 底层弹幕引擎

- 子弹 tick 更新统一由 `BulletEngine.step_bullets` 负责：年龄递增、行为解析、位置推进、擦弹/命中事件与出界裁剪。
- 擦弹不是“贴到子弹中心点”，而是玩家擦弹圆与子弹判定圆相交，且玩家受击圆与子弹判定圆未相交。
- 普通子弹以 `pattern_id:spawn_index` 作为默认 graze key，同一玩家同一弹体只计一次擦弹。
- 激光、长弹、持续判定体可以声明 `continuous_graze` 与 `graze_cooldown_ticks`，按每弹每玩家冷却 tick 重复触发擦弹。
- 主循环和平衡模拟必须共用同一套引擎判定，避免训练、回放和调参出现不同擦弹语义。

## Boss 弹幕类型覆盖

当前引擎用原创 pattern 数据覆盖正作 boss 常见类型，而不复制商业作品的符卡、命名、关卡编排或专有素材：

- `ring` / `alternating_ring`：均分环、交错环、奇偶 lane 变化。
- `spiral_stack`：多臂、多层、持续旋转螺旋。
- `n_way` / `burst` / `curve_fan`：自机狙、扇形、刀弹爆发、曲线 lane。
- `random_arc` / `grid_rain`：确定性随机弧、网格雨、错位墙。
- `split_chain` / `blossom` / `exploding_star`：延迟分裂、开花、星爆。
- `homing`：有限转向诱导，必须限制 turn rate 与 lifetime。
- `laser_curtain` / `sweep_laser`：预警激光、持续擦弹激光和扫射 lane。
- `orbital` / `curtain` / `sine_stream`：轨道释放、幕墙、波形流。
- `beam_sweep`：真实线段/胶囊判定的长光束，命中与擦弹都按点到线段距离计算。
- `wall_bounce`：边界反弹弹，适合封锁、折返和二次路线压迫。
- `morph_ring`：速度随角度波形变化的变形环。
- `summoner_orbit`：可移动弹源/使魔式周期发射器。
- `converge_cloud`：从外圈或随机云团向指定点收束的弹幕。

`BossPatternCatalog` 维护可审计的类型族：

- `radial`：环、交错环、多层螺旋、变形环。
- `aimed`：自机狙、扇形、刀弹、曲线 lane。
- `random_seeded`：确定性随机弧、网格雨、收束云。
- `delayed`：延迟分裂、开花、星爆。
- `tracking`：有限诱导与 baitable turning。
- `laser`：预警激光、扫射激光、胶囊长光束、持续擦弹激光。
- `field`：幕墙、波形流、轨道释放、召唤器、反弹 lane。

移植其他开源弹幕游戏设计时，只迁移机制语法和可复现参数结构；不得复制受版权保护的关卡、角色、音乐、美术、专名或完整弹幕编排。
当前迁移目录记录在 `BossPatternCatalog.OPEN_SOURCE_RECIPES`，每条 recipe 必须包含来源项目、许可证边界、映射到的原创 pattern types，以及 `mechanic_syntax_only` / `engine_concept_only` / `design_reference_only` 等非复制状态。

## Boss Spellbook 与阶段脚本

`BossSpellbookModel` 在单个 emitter 之上提供 boss 阶段脚本：

- `nonspell`：普通阶段，组合基础环、扇形、曲线 lane 等，用于建立节奏。
- `spell`：强化阶段，可同步多个 pattern families，例如激光预警 + 网格雨、召唤器 + 收束云。
- `last_spell`：终段压力，允许多族叠加但仍必须可由 seed/tick/config 重建。
- 每个 phase 声明 `duration_ticks`、`origin`、`motion`、`family_ids`、`recipe_id` 和 `patterns`。
- boss 位置支持静止、正弦、椭圆轨迹；pattern 在 tick 命中 interval 时由 `BulletPatternLibrary.emit_pattern` 发射。
- Spellbook recipe 只记录原创组合与机制来源边界，不复制任何商业符卡名、关卡脚本或开源项目 authored pattern。
