# 性能与弹幕上限

## 目标

- 渲染目标：60 FPS。
- 逻辑目标：单机和 v0.1 联机都按 60 tick/s 验收；如后续降到 30 tick/s，必须通过新 ruleset/protocol 版本切换。
- 普通机器上同屏弹幕稳定，不允许依赖处理落降低难度。

## 对象池

- 子弹、特效、道具、伤害数字都使用对象池。
- 不在高频 tick 中频繁创建和释放节点。
- 子弹死亡后回收到池，重置 owner、position、velocity、radius、flags。

## 批量绘制

- 同类子弹合批绘制。
- 避免每颗子弹独立复杂材质。
- 高密度弹幕下减少粒子和透明叠加。

## 上限策略

- 每个弹幕生成器配置最大弹数。
- 每场对局配置全局弹数上限。
- 接近上限时优先延迟非关键装饰弹。
- 超过上限时记录性能事件，不静默改变对局规则。

## 指标

- frame_time_ms。
- logic_tick_ms。
- bullet_count。
- collision_check_count。
- dropped_frame_count。
- correction_count。

## 验收

压力弹幕下仍可稳定操作低速移动和 Bomb。Replay 多次播放不应因帧率不同产生不同结果。
