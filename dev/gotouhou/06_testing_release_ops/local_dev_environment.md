# 本地开发环境

## 依赖

- Godot 4.7。
- Docker Desktop 或兼容 Docker。
- Go。
- PostgreSQL 客户端工具可选。
- Nakama CLI 或 Docker 镜像。

Steam 商业层开发额外需要 Steamworks SDK、Steam AppID、合作伙伴后台权限和测试发行配置。这些不属于开源本地环境。

## 启动流程

1. 启动 PostgreSQL。
2. 启动 Nakama。
3. 编译 Go Runtime。
4. 运行数据库迁移和 seed。
5. 打开 Godot 项目。
6. 使用开发账号登录。

## 配置

开发配置应包含：

- Nakama host。
- HTTP port。
- WSS port。
- server key。
- ruleset_version。
- debug flags。

## 测试账号

至少准备：

- 新手账号。
- 全卡账号。
- 活动账号。
- 低段位账号。
- 高段位账号。

Steam 商业服测试账号需要在闭源测试环境配置，不写入开源 seed 数据。

## 验收

新开发者按文档操作，能在本地进入 1v1 测试对局。
