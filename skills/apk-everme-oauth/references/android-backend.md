# Android、业务后端与眼镜

## 组件职责

```text
Rokid 眼镜  ← 已有设备通道 →  Android APK
                                 │ 业务登录凭据
                                 ▼
                        自有后端 / MemoryGateway
                        ├── 业务账号、同意、设备绑定
                        ├── OAuth 加密存储与撤销任务
                        ├── 受限 MCP 适配器
                        └── 同一 owner 的持久 outbox
                                 │ 用户授权的 EverMe token
                                 ▼
                         EverMe 托管 OAuth MCP
```

眼镜语音/HUD 沿项目现有通道接入 APK 或后端。EverMe 不负责建立蓝牙连接、麦克风采集、TTS、传感器同步或 HUD 绘制；逐项验证对应 SDK 与实体设备，不能由 OAuth 成功推断它们可用。

## 业务 API 示例（由接入方实现，并非 EverMe 官方路由）

下表业务路由要求自身登录认证；owner 从认证上下文取值，不信任客户端提交的 user_id。下面路径可按既有架构调整：

| 方法与路径 | 建议返回/行为 |
|---|---|
| `GET /integrations/everme` | 状态、读写资格、授权可用性、当前 owner 的队列计数 |
| `POST /integrations/everme/authorize` | 确认产品披露版本并登记发起端绑定后，返回 authorization_url 与不含秘密的 attempt_id |
| `GET /integrations/everme/attempts/{id}` | 只读本人授权尝试状态 |
| `POST /integrations/everme/complete` | 采用 App Link 方案时，验证当前 owner、原 APK attempt 秘密与一次性 completion_handle 后激活 |
| `DELETE /integrations/everme` | 立即停用并排队 revoke |
| `GET /integrations/everme/tools` | 返回经过 allowlist 的工具名与 inputSchema |
| `POST /integrations/everme/context`、`/search`、`/save-fact`、`/save-turn` | 固定映射一个工具，后端检查授权、同意及参数 |

浏览器 OAuth callback 是另一条受控入口，不能依赖 APK 的 Authorization header。它只接受已登记的精确 HTTPS 回调，通过一次性 state、PKCE 与持久 attempt 的 owner/环境/授权代次关联验证；query 中的 owner、user_id 或登录标记不能替换该关联。还需完成下面的发起端回程验证，之后 APK 才能查询到已激活的连接。

### 授权回程与激活

选择已有架构能支持的一种绑定方式，不能只靠回调后轮询：

- **受信浏览器 session**：发起 OAuth 前已经建立与业务 owner 绑定的浏览器登录 session，回调同时匹配该 session 与 attempt。仅在别人打开转发 URL 后新建匿名 cookie，不证明它是原发起端。
- **已验证 Android App Link**：APK 为本次 attempt 生成随机秘密，仅将其摘要绑定到后端 attempt，并在本机按 owner/session generation 保存秘密。后端 callback 换码后加密保管 grant，状态为 `completion_pending`，禁止 MCP 读取、写入及后台同步。仅通过已验证、由本产品控制的 App Link 将短期一次性 `completion_handle` 回传 APK；状态接口、轮询、普通回调页面和日志都不能提供 handle。APK 必须有匹配的原本地 attempt，随后以当前业务登录身份提交 attempt_id、原秘密与 handle；后端原子验证 owner、授权代次、秘密摘要、handle、有效期及未消费状态后才激活。其他手机收到链接、换号或原 attempt 丢失均不能完成。App Link 无法验证或无法交给原 APK 时保持未激活，不能回退成凭轮询确认。

待完成 grant 与 handle 必须有短期失效时间；超时、取消、退出或账号/授权变化时禁用并清除 handle，持久排队撤销 grant，按撤销结果保留追踪。EverMe callback code、token 和 PKCE verifier 不经过 App Link，也不交给 APK。这里的 App Link 完成握手是接入方保护业务账号的设计，不是 EverMe 新增的协议端点。

`completion_handle` 必须由后端独立使用密码学安全随机数生成器产生，至少包含 128 位随机熵；只存摘要并绑定同一 attempt 的 pending grant。不能使用 attempt_id、state、原 APK 秘密或它们的可计算派生值代替，否则发起者无需收到回程也能自行完成。原 APK attempt 秘密同样使用密码学安全随机数。App Link 的 host/path 由可信配置固定，不接收请求中的任意 return URL。

建议产品状态：`disconnected`、`authorizing`、`completion_pending`、`connected`、`reauthorization_required`、`revocation_pending`、`unavailable`。内部 `refreshing` 状态可映射为暂不可操作。`connected` 说明回程验证后授权已激活；`read_active`/`write_active` 由实际授权 scope 与当前产品同意共同决定；`synced` 说明收到本次约定的写入回执，各自不要混用。

刷新结果未知且无法确认整条远程授权已撤销时，另保留 `revocation_unconfirmed`；界面明确本应用已停用、远程撤授权仍待确认。不要把这种状态渲染为“全部撤销成功”。

后端的 OAuth 错误不能伪装成本应用登录失效：例如用业务错误码/409 提示重新连接 EverMe，只有自己的登录凭据失效才触发 APK 登出。生产与测试环境由可信服务器配置选择，不由请求体传入任意环境。

## APK 授权界面

1. 披露哪些数据会发送给 EverMe，以及相关片段是否进入另一个模型；连接操作不能默默打开独立的数据共享许可。
2. 通过业务 API 申请 URL，按已验证 discovery 的 HTTPS host、port、path 校验；拒绝 userinfo、fragment、控制字符和未许可重定向。不要把 APK 登录 token 追加到浏览器 URL。
3. 通过系统浏览器或 Custom Tabs 打开；此步骤只代表浏览器已打开。
4. 采用 App Link 方案时，验证链接来源并以匹配的本地 attempt 完成上述握手；不相信链接里的 `connected=true`。`onResume` 仅查询后端状态，不能代替完成握手。
5. 查询和页面异步回调须检查发起操作时的 owner 和本地 session generation；换号、退出或页面销毁后丢弃旧响应。缺字段/离线时显示待确认，不默认成功。

以下是与框架无关的伪代码，需要接到实际 API、生命周期和主线程：

```text
ticket = snapshot(currentOwner, loginGeneration)
attemptSecret = randomSecret()
result = backend.authorize(disclosureVersion, hash(attemptSecret))
if ticket != currentLoginSnapshot(): discard result
persistLocalAttempt(result.attempt_id, ticket, attemptSecret)
validateAuthorizationUrl(result.url)
openSystemBrowser(result.url)

onVerifiedAppLink(attemptId, completionHandle):
    attempt = requireMatchingLocalAttempt(attemptId, currentLoginSnapshot())
    backend.complete(attempt.id, attempt.secret, completionHandle)
    // 后端使用当前登录身份核 owner，原子验证后才允许读写

onResume:
    status = backend.status(forOwner = ticket.owner)
    if ticket == currentLoginSnapshot(): render(status)
```

## 服务端隔离与队列

建议最小记录：

| 记录 | 关键字段 |
|---|---|
| OAuth client | 环境、issuer、client_id、精确 callback、registration 状态 |
| Connection | owner、client、authorization_id、revision、加密 grant、实际授权 scope、有效期、状态 |
| Attempt | state 摘要、owner、授权代次、加密 verifier、发起浏览器 session 或 APK 秘密摘要、完成 handle 摘要、失效时间、一次性 claim/完成状态 |
| Memory outbox | owner、环境、授权代次、同意版本、源记录 ID、payload hash、状态、attempts、lease |
| Revoke job | client 与授权关联、加密待撤 token、重试时间；不随用户级联删除 |

加密密钥通过部署环境的秘密管理注入，与业务 JWT 密钥分离。密文同时绑定 owner、environment、client_id 和 authorization_id；解密后也验证这些上下文，避免记录被错配。为每个异步任务保留发起时身份，不能在发送时重新“找当前账号”。

```text
snapshot = (owner, environment, authorization_id, consent_version, device_generation)
assertStillAllowed(snapshot)
memory = readMcpWithBoundedDeadline()
assertStillAllowed(snapshot)
context = boundedUntrustedMemory(memory)
assertStillAllowed(snapshot)
return context to model / current owner's glasses
```

将本地对话保存和 outbox 入队放在同一事务；发送前用原子 claim 防止两个 worker 同时发：

```text
pending（从未发送）→ sending（claim 已持久化）→ synced（约定成功回执）
                                     └→ unknown（可能已提交、无可靠回执）
pending → canceled（owner、许可、授权代次已变化）
```

只有从未发送的 `pending` 可以重启后继续；崩溃遗留的 `sending` 进入 `unknown`，不重新领取。当地幂等键防重复入队，不证明上游 exactly-once。若未来上游提供正式幂等键/查询回执合同，再有针对性地加入安全重试。

收到读取结果后再检查权限；发送写入前再检查权限。已发出的 HTTP 请求无法靠本地取消保证远端未执行，UI 和记录必须保留这一不确定性。未知写入不能转给旧数据库、共享凭据或新账号重发。

## 日志与运行行为

日志仅保留必要 request ID、阶段、耗时、状态和脱敏错误码。不要写入 token、verifier、code、state、attempt 秘密、completion_handle、Authorization、记忆正文、查询全文、用户对话或可泄露秘密的完整 URL。网络读取设截止预算；超时保留同 owner 的本地能力，不阻塞眼镜的正常运动流程。
