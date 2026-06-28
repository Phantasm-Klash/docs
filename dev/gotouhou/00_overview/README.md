# 00 Overview

本阶段定义项目边界、术语来源、技术选择、开源边界、i18n 和开发路线。任何后续实现与平衡争议，都优先回到本阶段文档确认原则。

## 目标

- 明确 gotouhou 是原创主题弹幕卡牌 PVP，而不是东方 Project 官方衍生素材集合。
- 明确东方内容只作为可替换主题包和 Steam 创意工坊 Mod 进入，不作为基础发行内容。
- 把 STG 术语转成可实现的客户端、服务端和对局系统。
- 确定轻量客户端、权威服务端、可复现 Replay 的基础路线。

## 交付物

- `terminology_mapping.md`：STG 术语到系统功能的映射。
- `tech_stack.md`：Godot、Nakama、PostgreSQL 及备选技术。
- `open_source_boundary.md`：GitHub 开源内容、闭源 Steam 商业层和服务器版本边界。
- `network_security_and_server_split_plan.md`：Nakama/Go 业务服务器、C++ Battle Server、业务 HTTPS/WSS 安全 envelope、战斗 ECDHE/KCP/protobuf/ChaCha20、仓库拆分和迁移计划。
- `i18n_and_theme_policy.md`：基础文本、东方主题文本和多套美术资源的替换策略。
- `asset_and_license_policy.md`：开源素材授权政策。
- `roadmap.md`：阶段性开发和验收条件。
- `../02_networked_match/deterministic_lockstep_review.md`：确定性帧同步路线复盘、当前客户端/服务端/协议能力检查和迁移验收顺序。

## 验收标准

- 开发者可以根据本目录判断某个功能是否属于 v1。
- 客户端、服务端、素材、i18n、开源边界和上线策略有明确默认方案。
- 所有阶段目录都能从本目录追溯到设计目的。
