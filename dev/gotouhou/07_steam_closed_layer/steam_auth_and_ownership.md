# Steam 登录与购买校验

## 目标

官方商业服必须确认玩家拥有 Steam App 后才允许登录。开源服务器不包含此逻辑。

## 登录流程

1. Steam 客户端启动游戏。
2. 游戏客户端通过 Steamworks 获取 Auth Session Ticket。
3. 客户端把 ticket 发送给官方登录服务。
4. 官方服务端调用 Steam 受信接口校验身份。
5. 官方服务端确认该 SteamID 拥有 App。
6. 校验通过后映射或创建 Nakama 用户。
7. 返回游戏 session。

## 失败场景

- Steam 未运行。
- ticket 过期。
- App 未购买。
- 账号被封禁。
- 官方服务不可用。

## 数据映射

官方商业服保存：

- steam_id。
- nakama_user_id。
- first_seen_at。
- last_seen_at。
- ownership_verified_at。
- ban_status。

## 安全

- 客户端不能自行声明 SteamID。
- 购买校验必须在服务端执行。
- Steam Web API Key 不进入开源仓库。
