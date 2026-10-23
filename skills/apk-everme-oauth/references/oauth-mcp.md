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

这些 scopes 是声明的支持集。当前参考应用申请全集；其他产品是否允许子集、是否需要商务登记，以接入方最新合同为准。不要从 `scopes_supported` 推导任意组合已获准。平台标识、图标、产品名或回调白名单如需预登记，独立完成；DCR 不替代这一资格确认。

## 可复用的 OAuth 交换形状

下面是**请求形状**，不是可直接运行的凭据配置。`example.com` 是占位域名，部署前替换成自己的 HTTPS 回调；固定精确匹配，不用前缀、通配符或请求体自选回调。

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

授权码 token 请求为 `application/x-www-form-urlencoded`：`grant_type=authorization_code`、`client_id`、`code`、相同 `redirect_uri`、`code_verifier`、相同 `resource`。不发送 client secret。不要打印完整回调 query 或 token 响应；回调页只显示简短结果并设置 `Cache-Control: no-store`、`Referrer-Policy: no-referrer`。

刷新使用 `grant_type=refresh_token`、相同 `client_id`、当前 `refresh_token`；resource 参数遵循采用的 MCP/OAuth 版本与供应方合同。按授权链做跨进程单飞/数据库 compare-and-swap，网络前持久标记处理中，成功后原子更换整对 token 及有效期。有效期来自实际响应，不能硬编码历史手册中的时长。

发出换码或刷新后结果未知时，不重放同一 code/旧 refresh token。让连接进入恢复或重新授权状态；晚到的 token 若对应 owner/授权代次已失效，只进入撤销队列，不重新连接旧账号。

revoke 的参考表单：`client_id`、`token=<refresh token>`、`token_type_hint=refresh_token`。断开先阻断业务使用，再持久执行撤销；遇到网络故障/503 保留 `revocation_pending`。是否同时撤销整条授权链，以供应方合同和测试为准。远程历史删除不是 revoke 的含义。

如果 refresh 实际已轮换而回执丢失，旧 token 的 revoke 返回 200 也不能证明未知的新 token 或整条授权链已撤销：[RFC 7009 §2.2](https://www.rfc-editor.org/rfc/rfc7009#section-2.2) 规定无效 token 也可返回 200。此时保持本地禁用和 `revocation_unconfirmed` 的授权链追踪，按供应方已支持的账号端撤授权或支持渠道确认；不能凭旧 token 的成功回执关闭该追踪。已不再需要的旧秘密可以按保留策略清除，未确认状态和恢复所需的非秘密关联信息仍应保留。

## MCP 生命周期与工具

优先使用维护中的 MCP SDK。自行实现时支持 Streamable HTTP 的 JSON 与 SSE 两类响应、JSON-RPC ID 匹配、大小/时间预算，并按采用版本协商：

```text
POST initialize → 校验协商 protocolVersion 与 capabilities
POST notifications/initialized
POST tools/list → 读取所有 nextCursor 分页并验证目录
POST tools/call → 校验输入 schema + 检查 JSON-RPC error / result.isError
```

HTTP 使用 `Authorization: Bearer <access token>`，`Accept: application/json, text/event-stream`；后续请求带协商的 `MCP-Protocol-Version`。若 initialize 响应有 `Mcp-Session-Id`，后续请求必须携带并按授权代次隔离。会话 404 应重新 initialize；重建会话不等于可以重发之前结果未知的写入。服务器未分配 ID 时可使用无状态方式，不能照搬参考应用的无状态假设到所有 MCP 服务。

当前工具名参考如下；**参数以目标远程服务的认证后 `tools/list` 为准**。只允许实际需要的工具，不能做任意 URL/method/header 的匿名代理。

| 工具 | 用途 | 适配时检查 |
|---|---|---|
| `mem_context` | 用户资料上下文 | 是否需要 query、是否支持 forceRefresh；不要当实时运动状态 |
| `mem_search` | 相关历史检索 | 短关键词，避免整段聊天；核对 query 类型，显式设 topK |
| `mem_save_fact` | 经许可的持久事实/偏好 | 核对 fact 或 messages 形状；不把推断写成确认事实 |
| `mem_save_turn` | 完整对话轨迹 | messages 角色、顺序、toolCalls/toolCallId 对应关系及 flush 语义 |

适配器可以从下列**候选输入**开始，但只有实际 schema 接受且数据许可有效才可发送：

```json
{"name":"mem_search","arguments":{"query":"骑行 偏好","topK":5}}
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
