# 版本、接入选择与来源

资料核对日期：2026-10-24（Asia/Shanghai）。网页与主分支会变化；实施时重新核对目标部署，不能用本文件声称已完成实时服务验证。

## 名称与路线

| 路线 | 连接方式 | 开发者要准备什么 |
| --- | --- | --- |
| EverOS Cloud v2 | AIUI → `https://api.evermind.ai/api/v2/memory/*` | Cloud 账号、API key、用户数据隔离、可达网络 |
| EverOS 自建 v2 | AIUI → 自己的 HTTPS 入口 → EverOS | Python 服务、模型服务、持久化目录，以及入口认证/授权 |
| 共享产品的无 APK 接入 | AIUI → 自有认证网关 → Cloud 或自建 EverOS | 网关按已认证主体固定用户与作用域；主 key 保留服务端 |
| EverMe | OAuth + MCP，个人记忆账号授权 | 另用 APK/EverMe Skill；不能以 EverOS API key 代替用户 OAuth |

EverMind 是组织/生态名；当前官方仓库名称为 **EverOS**。不要将用户口语中的 Evermate、Evermind OS 自动当成有独立端点的产品。

自建 EverOS 以 Markdown 为持久化源，SQLite 与 LanceDB 提供索引。官方默认仅绑定 `127.0.0.1:8000`，**没有内建鉴权**。`127.0.0.1` 在眼镜上指眼镜自己，并非开发电脑；不要让眼镜连接裸露的无鉴权公网服务。开发最低配置需要可用 LLM；仅 LLM 时明确选 `keyword`，不能假设默认 `hybrid` 可用。来源：[README](https://github.com/EverMind-AI/EverOS)、[Quickstart](https://github.com/EverMind-AI/EverOS/blob/main/QUICKSTART.md)、[Security](https://github.com/EverMind-AI/EverOS/blob/main/SECURITY.md)。

## 版本分支不能混用

- Cloud 新接入与当前 OSS 均使用 v2；旧服务看到 `/api/v0` 或 `/api/v1/memories` 时，先确认具体提供商版本和迁移映射，不做路径字符串替换。
- 官方公告：Cloud v1 计划于 **2026-11-02 10:00（北京时间）** 停用。Cloud v1 退役不等于 OSS `/api/v1` 兼容别名同时消失。[迁移公告](https://docs.evermind.ai/api-reference/v1-sunset)
- 资料存在更新时差：官方 `llms.txt` 曾将异步 task 列为 Cloud-only，但下面固定 OSS 提交的 `docs/api.md` 已支持异步队列与 `/api/v2/tasks/*`。Cloud 默认异步、此 OSS 版本默认同步；示例显式设 `async_mode:false`，并仍处理 202。不要按部署名称硬编码是否支持任务查询。
- `app_id/project_id/user_id` 是数据范围；Cloud 租户由 API key 决定。共享一个主 key 后让客户端自由填写 `user_id`，不能建立用户之间的安全边界。[Add API](https://docs.evermind.ai/api-reference/memory/add-messages-%5Boss-%2B-cloud%5D)

## 固定的官方源码快照

| 来源 | 核对提交 | 重点 |
| --- | --- | --- |
| EverOS | [`5b0979b1b7f3a0cbe235756ff098515ec490753e`](https://github.com/EverMind-AI/EverOS/tree/5b0979b1b7f3a0cbe235756ff098515ec490753e) | `docs/api.md`、`QUICKSTART.md`、`SECURITY.md` |
| AIUI | [`a27bb7a83f0e31a9749ba451ddf5c8686131a3df`](https://github.com/yodaos-project/AIUI/tree/a27bb7a83f0e31a9749ba451ddf5c8686131a3df) | `skills/aiui-dev/references/apis/wx.md`、`framework.md` |

官方在线入口：[API 总览](https://docs.evermind.ai/api-reference/introduction)、[Cloud 控制台](https://everos.evermind.ai)、[AIUI 开发文档](https://js.rokid.com/AIUI/)。

本 Skill 随包维护 JavaScript SDK v0.1.0，针对 AIUI `wx.request` 提供无 Node 依赖的接线与生命周期处理；唯一实现在 `sdk/index.js`，旧 `.mjs` 入口只作兼容导出。它属于社区适配器，不与官方 [EverOS Python SDK](https://github.com/EverMind-AI/everos-cloud-sdk-python) 或 EverMe 的 agent-sdk 混称。公开案例 [AIUI-Sports-Agents](https://github.com/EasonZhu1997/AIUI-Sports-Agents/tree/1f34da442a830cfa571881cd6d81cb4eee08cc84) 展示原应用的可选记忆边界；该固定快照并未使用新 SDK。

本 Skill 的工程经验来自 AIUI 跑步应用参考实现：本地先呈现、可选云记忆、身份隔离和迟到响应保护。该应用原有服务端路由并非 EverOS 官方 REST 契约；本 Skill 未复制业务域名、凭据、私有数据或专有后端实现，也不声称该应用已迁移到直连 v2。
