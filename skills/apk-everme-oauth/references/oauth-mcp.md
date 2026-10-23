# EverMe OAuth 与远程 MCP

## 合同来源和 discovery

下表来自 2026-10-24 对官方公开 discovery 的无凭据 GET，两个响应均为 HTTP 200。它证明端点与声明能力，不证明某个产品已获接入资格，亦不证明读写成功。实施时重新读取并核对受信任 issuer；若端点改变，先查官方说明，不向任意新地址发送 token。

| 字段 | 当次公开值 |
|---|---|
| issuer | `https://api.everme.evermind.ai` |
| resource | `https://api.everme.evermind.ai/mcp` |
| protected resource metadata | `https://api.everme.evermind.ai/.well-known/oauth-protected-resource` |
| authorization server metadata | `https://api.everme.evermind.ai/.well-known/oauth-authorization-server` |
| authorization / token / registration / revocation | 同 issuer 下 `/oauth/authorize`、`/oauth/token`、`/oauth/register`、`/oauth/revoke` |
| response / grants | `code`；`authorization_code`、`refresh_token` |
| PKCE / token endpoint auth | `S256` / `none` |
| scopes_supported | `mem:read`、`mem:search`、`mem:write` |

这些 scopes 是声明的支持集。[通用接入手册](https://my.feishu.cn/wiki/GmuYwZckviPTfBk7mwJcsCTZnsy?from=from_copylink)（文档版本 2026-09-18，本次核对 2026-10-24）明确允许全集或子集；省略 scope 默认 `mem:read mem:search`，需要写入时必须显式申请 `mem:write`。按产品必要范围申请，保存 token 响应的实际授权 scope，用它驱动 `read_active`、`write_active` 与工具准入；不能把 discovery 支持集或申请集直接当已获授权。响应省略 scope 时按 OAuth 规则及已确认的请求默认值解释，不补齐为全集。

该手册将所有环境的精确回调 URL 白名单登记列为 DCR 前置要求；本后端方案使用自有 HTTPS 回调，手册的 localhost 调试示例不代表生产回调可省略登记。未登记主机可能返回 `400 invalid_client_metadata`。`client_name` 须与 EverMe 约定后固定，不拼环境或版本；名称不符可能静默显示通用图标，注册后不能修改。部署环境仍分别持久保存 client 记录，不能把不同回调或环境混用。DCR 不替代这些供应方登记要求。

## 可复用的 OAuth 交换形状

下面是**请求形状**，不是可直接运行的凭据配置。`example.com` 是占位域名，部署前替换成已完成白名单登记的自有 HTTPS 回调；固定精确匹配，不用前缀、通配符或请求体自选回调。`YourProduct` 替换为已与 EverMe 约定的固定名称。

DCR 使用 JSON，将成功返回的 `client_id` 持久保存，并按环境复用；不要每次连接都注册。参考形状：

```json
{
  "client_name": "YourProduct",
  "redirect_uris": ["https://api.example.com/integrations/everme/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "token_endpoint_auth_method": "none"
}
```

授权 URL 参数使用正规的 URL 编码器：

```text
response_type=code
client_id=<persisted client ID>
redirect_uri=<exact registered callback>
scope=<provider-approved scopes>
state=<fresh random single-use state>
code_challenge=<base64url(SHA256(verifier)), without padding>
code_challenge_method=S256
resource=<discovered canonical resource>
```

每次生成新的 RFC 7636 verifier（43–128 个许可字符）；state 在持久库中保存摘要、失效时间和业务 owner、环境、client、授权代次，verifier 使用独立密钥加密。回调在事务内一次性 claim state，再换码；旧 state、重复回调、换号、配置变化都应拒绝。

还必须验证回程属于发起授权的用户代理：[RFC 9700 §2.1.1](https://www.rfc-editor.org/rfc/rfc9700#section-2.1.1) 要求 PKCE challenge 与发起客户端及 user agent 安全绑定。只有 `state → owner` 的数据库关联不够：攻击者可将自己业务账号取得的合法授权 URL 转给另一人，后者授权后会被错误绑定到攻击者的 owner。采用与该 owner 一致的受信浏览器登录 session 验证回程；或采用 [Android 与后端](android-backend.md#授权回程与激活) 的 App Link 完成绑定，在验证前将换得的 grant 保持为不可使用的 pending 状态。普通轮询成功、回调收到合法 state 或打开浏览器，都不能替代这一检查。

授权码 token 请求为 `application/x-www-form-urlencoded`：`grant_type=authorization_code`、`client_id`、`code`、相同 `redirect_uri`、`code_verifier`、相同 `resource`。不发送 client secret。不要打印完整回调 query 或 token 响应；回调页只显示简短结果并设置 `Cache-Control: no-store`、`Referrer-Policy: no-referrer`。

刷新使用 `grant_type=refresh_token`、相同 `client_id`、当前 `refresh_token`；resource 参数遵循采用的 MCP/OAuth 版本与供应方合同。手册说明每次同时轮换 access/refresh token，旧 refresh 立即失效，重放会撤销整条 token 链。按授权链做跨进程单飞/数据库 compare-and-swap，网络前持久标记处理中，成功后原子更换整对 token、实际 scope 及有效期。有效期来自实际响应，不能硬编码手册示例时长。相同 EverMe 用户与 client 重复授权会复用 Agent 并使旧 token 失效，重新授权也要推进本地授权代次。

手册当前允许省略 resource，但携带时必须等于 discovery 的 resource，换码值须与授权请求一致；它可被供应方配置为强制。采用本 Skill 引用的 MCP 2025-06-18 基线时，授权与 token 请求仍必须包含 resource；不要把服务当前宽松校验写成 MCP 的通用规则。

发出换码或刷新后结果未知时，不重放同一 code/旧 refresh token。让连接进入恢复或重新授权状态；晚到的 token 若对应 owner/授权代次已失效，只进入撤销队列，不重新连接旧账号。

revoke 的参考表单：`client_id`、`token=<refresh token>`、`token_type_hint=refresh_token`。断开先阻断业务使用，再持久执行撤销；遇到网络故障或手册所述 `503 / errno 30408` 保留 `revocation_pending` 并重试。手册说明有效 refresh token 的 revoke 会撤销整条链并使 Agent/access token 失效；未知、跨 client 或已撤 token 也返回 200 空体，因此只把有对应有效授权证据的回执解释为已撤销。真实撤销行为仍需已授权联调验证，远程历史删除不是 revoke 的含义。

如果 refresh 实际已轮换而回执丢失，旧 token 的 revoke 返回 200 也不能证明未知的新 token 或整条授权链已撤销：[RFC 7009 §2.2](https://www.rfc-editor.org/rfc/rfc7009#section-2.2) 规定无效 token 也可返回 200。此时保持本地禁用和 `revocation_unconfirmed` 的授权链追踪，按供应方已支持的账号端撤授权或支持渠道确认；不能凭旧 token 的成功回执关闭该追踪。已不再需要的旧秘密可以按保留策略清除，未确认状态和恢复所需的非秘密关联信息仍应保留。

## MCP 生命周期与工具

优先使用维护中的 MCP SDK。自行实现时支持 Streamable HTTP 的 JSON 与 SSE 两类响应、JSON-RPC ID 匹配、大小/时间预算，并按采用版本协商：

```text
POST initialize → 校验协商 protocolVersion 与 capabilities
POST notifications/initialized
POST tools/list → 读取所有 nextCursor 分页并验证目录
POST tools/call → 校验输入 schema + 检查 JSON-RPC error / result.isError
```

HTTP 使用 `Authorization: Bearer <access token>`，`Accept: application/json, text/event-stream`；后续请求带协商的 `MCP-Protocol-Version`。手册说明当前 `/mcp` 返回 SSE，同时客户端仍需支持 JSON；缺少所需 Accept 时可能返回 `406` 纯文本，所以先检查 HTTP 状态与 Content-Type，再解析协议响应。已接受的 notification 可返回 202 空体，不应按 JSON 解析。

手册的 HTTP 错误 JSON 中 `body.status` 是供应方 errno，不是 HTTP 状态码。按二者分流，不对所有 401 自动刷新：

| HTTP / body.status | 含义 | 动作 |
|---|---|---|
| 401 / 30301 | token 无效 | 重新授权 |
| 401 / 30302 | 已撤销或断开 | 保持停用，重新连接 |
| 401 / 30305 | access token 过期 | 按单飞与未知结果规则刷新 |
| 403 / 30303 | scope 不足 | 保持缺少的读写能力禁用，按需重新申请权限 |

401 的 `WWW-Authenticate` 可提供 `resource_metadata`；解析它时仍应用前面的 issuer/端点信任检查，不能向挑战中任意地址发送 token。这些 EverMe 错误不代表 APK 自身登录过期。

手册声明支持 `2024-11-05`、`2025-03-26`、`2025-06-18`、`2025-11-25`，缺少版本头时默认 `2025-03-26`；这是当前供应方说明，客户端仍须校验实际协商结果。若 initialize 响应有 `Mcp-Session-Id`，后续请求必须携带并按授权代次隔离。会话 404 应重新 initialize；重建会话不等于可以重发之前结果未知的写入。服务器未分配 ID 时可使用无状态方式，不能照搬参考应用的无状态假设到所有 MCP 服务。

以下语义已按上述手册核对；**部署时仍以目标远程服务认证后的 `tools/list` 核对实际 schema**。只允许实际需要且实际授权 scope 覆盖的工具：`mem_context` 对应 `mem:read`，`mem_search` 对应 `mem:search`，两个保存工具对应 `mem:write`。不能做任意 URL/method/header 的匿名代理。

| 工具 | 用途 | 适配时检查 |
|---|---|---|
| `mem_context` | 只读持久 Profile，每 session 通常一次 | query 已废弃且被忽略；forceRefresh 默认 false；不要当实时运动状态或历史检索 |
| `mem_search` | 相关历史检索 | 2–8 个关键词、约 100 字符内，topK 默认 10；仅在用户明确聊天时间时使用时间窗；临时未提取 transcript 不是已确认事实 |
| `mem_save_fact` | 经许可的持久事实/偏好 | fact 或仅含 user/assistant 的 messages，不接受 tool；flush 默认 true；extracted/profileUpdated=true 才证明进入 Profile |
| `mem_save_turn` | 完整对话轨迹 | 优先保存真实完整 messages 与 toolCalls/toolCallId 对应关系；flush 默认 true；单消息不能提取 agent_case/skill，不虚构工具往返凑轨迹 |

`mem_save_fact` 返回 `accepted:true` 仅说明接收；`status:no_extraction` 表示未提取，不能告诉用户“已记住”，也不能自动重复写入。用实际 `extracted` / `profileUpdated` 回执判断提取和 Profile 更新，后续可检索仍单列验证。

以下示例按手册语义编写，只有实际 schema 接受且数据许可有效才可发送。用户明确陈述偏好时优先使用 `mem_save_fact`，保存对话轨迹另用 `mem_save_turn`，不要从后者的接收回执推断 Profile 已更新：

```json
{"name":"mem_search","arguments":{"query":"骑行 偏好","topK":5}}
```

```json
{"name":"mem_save_fact","arguments":{"fact":"用户明确表示喜欢周末上午骑车。","flush":true}}
```

```json
{
  "name": "mem_save_turn",
  "arguments": {
    "messages": [
      {"role":"user","content":"我喜欢周末上午骑车，请记住这个偏好。"},
      {"role":"assistant","content":"已记录本次记忆请求；云端同步状态会单独显示。"}
    ],
    "sessionKey":"demo-conversation-001",
    "flush":true
  }
}
```

`sessionKey` 是会话关联值，不是已验证的幂等键。成功 HTTP 状态、MCP 成功结果、原始消息落库、派生记忆提取和随后可检索是不同事件。保留供应方回执含义；只有实际支持对账时才能把 `unknown` 转成确认状态。

公开客户端仓库还提供 `mem://profile`、`mem://search` 只读资源；这不是远程托管 OAuth 服务一定实现相同资源的证据。CLI 的 Device Flow、agent token 和本地 stdio 插件安装流程也不能代替 APK 的用户 OAuth 授权。
