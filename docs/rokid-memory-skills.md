# Rokid 开发者：两条长期记忆接入路线

把长期记忆接到眼镜应用时，先选实际运行链路。本仓库提供两份可以独立复制、交给 AI 编程助手使用的 Skill，适用于新应用接入、既有项目改造和故障排查。

| 选择 | AIUI × EverOS | Android APK × EverMe |
| --- | --- | --- |
| Skill | [`aiui-everos-direct`](../skills/aiui-everos-direct/SKILL.md) | [`apk-everme-oauth`](../skills/apk-everme-oauth/SKILL.md) |
| 入口 | AIUI Page / Widget / Agent Worker | Android 手机辅助应用 |
| 接入方式 | AIUI HTTP 请求可达的 EverOS 服务 | 用户 OAuth 授权后调用远程 MCP |
| 手机 APK | 不作为依赖 | 承担登录入口、应用交互和眼镜连接 |
| 服务与凭据 | 确认云版或自建版、API 版本、地址和认证 | OAuth discovery、PKCE、token 生命周期、MCP 工具发现 |
| 典型任务 | 记住用户偏好，检索相关历史后生成回复 | 经用户同意使用个人记忆，辅助眼镜中的连续对话 |

AIUI 的“直连”表示不依赖手机 APK 转发，仍然需要眼镜可访问的服务。注册账号只是准备工作之一；服务开通、凭据、网络、用户隔离和真实读写都需要核验。普通应用的数据目录或 `user_id` 参数本身不构成访问控制。

APK 路线需要先与 EverMe 登记各环境的准确回调 URL、约定固定的 `client_name`，再执行客户端动态注册。后端除校验 state 和 PKCE，还须验证授权结果回到原浏览器会话或原 APK；只轮询“已连接”不足以防止转发授权链接造成账号错绑。具体要求见 APK Skill 的 OAuth 与后端参考。

这里采用上游正式名称 **EverOS / EverMe**。“Evermind OS”“Evermate”等口头称呼需要先按用户提供的实际服务地址确认，不能推导出另一套 API。EverMe 公开 CLI/plugin 和远程 OAuth MCP 也可能提供不同工具；应读取目标服务的发现结果。

## 取得与使用

1. 克隆或下载 [Eason-Agent-Skills](https://github.com/EasonZhu1997/Eason-Agent-Skills)。
2. 复制所需的整个 `skills/aiui-everos-direct` 或 `skills/apk-everme-oauth` 目录，包括 references、agents、LICENSE 和存在的示例文件。
3. 按你使用的 AI 编程助手的技能安装方式放入目录，或直接让助手先读取该目录中的 `SKILL.md`。不需要同时安装两份，也不要求安装作者的其他技能。
4. 提供你的项目、目标固件/SDK、选择的记忆服务和已经完成的验证。密钥使用本机安全配置，不写进聊天、仓库或公开安装包。

AIUI 调用示例：

```text
使用 $aiui-everos-direct，为我的 AIUI 项目接入 EverOS 长期记忆。
不依赖手机 APK。先核对现有 AIUI 网络 API、实际 EverOS 服务版本和用户隔离，
实现记忆写入与检索，给出可运行验证及未完成的眼镜实测项。
```

APK 调用示例：

```text
使用 $apk-everme-oauth，为我的 Android 手机辅助应用接入 EverMe，供 Rokid 眼镜对话使用。
沿用现有账号和后端，实现系统浏览器授权、PKCE、MCP 工具发现、刷新和解绑，
并验证账号切换、取消授权、网络超时与重复回调。先完成本地实现和测试。
```

排查示例：

```text
按对应 Skill 检查：写入请求成功但检索不到，或手机解绑后旧请求仍返回记忆。
先区分服务接受、处理完成、检索可见和客户端回调归属，不要直接循环重发写入。
```

## 本次分享包含什么

包含可执行工作流程、版本与协议差异、通用集成方法、合成示例及验收清单。说明由公开上游资料和作者 AIUI/APK 项目经验整理；不附真实凭据、个人记忆或私有业务源码。

Skill 文档与本地检查通过，只说明这些分享材料通过对应验证。账号授权、云端写入、正式应用构建、安装和物理眼镜效果仍须由使用者在自己的目标环境验证，不能从本仓库发布状态推断已经通过。

来源与验证范围见各技能的 references，以及 [发布验证记录](validation.md)。本项目为社区分享，许可证为 MIT；不代表 Rokid 或 EverMind 的官方产品认证。
