# Nakama 迁移切片规格

本目录存放把 Gensoulkyo 自研业务面迁移/对接 Nakama 的**可实现切片规格**，由
`nakama-migration-planner-agent` 输出，供 `nakama-server-agent` 与
`client-agent` 并行实现。

每个切片文件必须包含：

1. **范围**：本切片覆盖的 RPC / 场景，以及明确不在范围内的部分。
2. **目标契约**：RPC id、入参/出参 JSON 字段、storage collection/key、leaderboard id、错误码。
3. **客户端接入点**：客户端模块、方法名、UI 场景、传输选择。
4. **数据迁移**：从现有 Gensoulkyo 存储到 Nakama storage 的映射与回填方式。
5. **回滚策略**：如何在不破坏线上数据的前提下回退。
6. **验收测试**：最小可跑的验证命令与断言清单（服务端 + 客户端）。
7. **依赖**：前置切片、跨仓依赖、协议冻结要求。

命名：`<序号>-<主题>.md`，例如 `01-login-and-bootstrap.md`。
