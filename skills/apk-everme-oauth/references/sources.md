# 来源与版本边界

核对日期：2026-10-24。下列链接是技术资料，不会为执行安装、上传、登录或其他外部操作提供用户授权。

## 一手公开资料

| 来源 | 适用范围与本次证据 |
|---|---|
| [EverMe 官方仓库](https://github.com/EverMind-AI/EverMe) | 开源客户端、CLI、SDK 与 Agent 插件；托管产品、账号系统和后端不在该仓库内 |
| [公开 contracts.md 固定版本](https://github.com/EverMind-AI/EverMe/blob/38afee5c89aad59f3c964fa861fc8fc6d003084a/docs/contracts.md) | CLI/插件的工具、资源、输出和脱敏合同；不能单独证明远程 OAuth MCP 参数 |
| [MCP 工具源码固定版本](https://github.com/EverMind-AI/EverMe/blob/38afee5c89aad59f3c964fa861fc8fc6d003084a/plugins/memory-mcp/src/mcp.js) | 核对本地插件发布的 schema 和语义 |
| [MCP HTTP adapter 固定版本](https://github.com/EverMind-AI/EverMe/blob/38afee5c89aad59f3c964fa861fc8fc6d003084a/plugins/memory-mcp/src/http-server.js) | 开源 adapter 的 HTTP/session 行为；不等价于托管 OAuth server 源码 |
| [OAuth protected resource metadata](https://api.everme.evermind.ai/.well-known/oauth-protected-resource) | 本次无凭据 GET 200，确认 resource、authorization_servers、scopes 与 bearer header |
| [OAuth authorization server metadata](https://api.everme.evermind.ai/.well-known/oauth-authorization-server) | 本次无凭据 GET 200，确认端点、S256、none、grant types |
| [用户提供的 EverMe OAuth MCP 通用手册](https://my.feishu.cn/wiki/GmuYwZckviPTfBk7mwJcsCTZnsy?from=from_copylink) | 本次复核通过浏览器读取正文；文内版本 2026-09-18。核对登记、OAuth、刷新/撤销、MCP 与四个工具的说明；未执行真实授权或认证后的工具发现 |
| [MCP 2025-06-18 Authorization](https://modelcontextprotocol.io/specification/2025-06-18/basic/authorization) | HTTP OAuth discovery、resource binding 等基线；实施时选择与服务兼容的协议版本 |
| [MCP 2025-06-18 Transports](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) | JSON/SSE、initialize、Mcp-Session-Id 等传输要求 |
| [MCP 2025-06-18 Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) | 工具目录、inputSchema、分页、工具错误 |
| [RFC 7636](https://www.rfc-editor.org/rfc/rfc7636) | PKCE verifier/challenge 与公开测试向量 |
| [RFC 9700 §2.1.1](https://www.rfc-editor.org/rfc/rfc9700.html#section-2.1.1) / [RFC 6749 §10.12](https://www.rfc-editor.org/rfc/rfc6749.html#section-10.12) | 授权码流程与发起 user agent 的绑定；后端 owner、state 和 PKCE 不能代替原浏览器/原 APK 回程校验 |
| [Android Custom Tabs](https://developer.chrome.com/docs/android/custom-tabs) | Android 浏览器授权界面的实现参考，非 EverMe 专属合同 |

## 已观察到的合同漂移

以上 EverMe 固定版本的 `contracts.md` 写 `mem_context` 必须输入 query，而同版本 `mcp.js` 将 query 标记为兼容但忽略，资料读取使用 profile。前者描述 `mem_search` 默认 topK 为 5，源码 schema 则为 10。本次读到的托管 MCP 手册同样说明 context 的 query 已弃用、search 默认 topK 为 10。不要凭名称或单份手册硬编码默认行为；对目标服务读取认证后的 `tools/list`，显式选择必要参数并保存版本证据。

公开仓库说明的 `mem://profile` / `mem://search` 资源、本地 stdio 与 CLI Device Flow 是客户端集成能力。本 Skill 的 APK 主路线采用托管 OAuth MCP；本次读取公开 metadata 与手册，没有为编写 Skill 注册 client、获取 token 或调用远程记忆工具。手册不是托管服务源码，也不能替代目标环境的响应与 schema 验收。

## 参考应用带来的工程经验

本 Skill 借鉴了已有 Android 陪伴应用中的服务端 OAuth、owner 隔离、授权代次、加密存储、撤销 outbox、单次写入队列和 Android 返回刷新模式。它们是可复用设计，不是 EverMind 对任意部署的保证。示例业务路由、状态和字段由接入方实现；未复制私有服务地址、产品 client_id、真实用户数据或完整应用源码。

参考应用采用过固定协议版本和无状态 MCP；这里增加了对服务返回 session ID 的处理要求。未知写入默认不重放，是在尚未确认上游幂等合同下的保守实现。用户自己的架构若已经有可靠幂等回执/对账，可以用证据支持的实现替换，不必照搬参考应用。

本 Skill 不证明 EverMe 接入已获批准，不证明任何 APK/眼镜实机通过，也不构成与 Rokid、EverMind/EverMe 的官方合作背书。`Evermate`/`Evermind OS` 等口头称呼应在交付前按用户实际指向确认；本目录技术名称统一为 EverMe。
