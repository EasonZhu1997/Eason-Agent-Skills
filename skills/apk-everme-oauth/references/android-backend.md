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
| `POST /integrations/everme/authorize` | 确认产品披露版本后返回 authorization_url 与不含秘密的 attempt_id |
| `GET /integrations/everme/attempts/{id}` | 只读本人授权尝试状态 |
| `DELETE /integrations/everme` | 立即停用并排队 revoke |
| `GET /integrations/everme/tools` | 返回经过 allowlist 的工具名与 inputSchema |
| `POST /integrations/everme/context`、`/search`、`/save-fact`、`/save-turn` | 固定映射一个工具，后端检查授权、同意及参数 |

浏览器 OAuth callback 是另一条受控入口，不能依赖 APK 的 Authorization header。它只接受已登记的精确 HTTPS 回调，通过一次性 state、PKCE 与持久 attempt 的 owner/环境/授权代次关联验证；query 中的 owner、user_id 或登录标记不能替换该关联。回调结果再由 APK 使用自身登录身份查询。

建议产品状态：`disconnected`、`authorizing`、`connected`、`reauthorization_required`、`revocation_pending`、`unavailable`。内部 `refreshing` 状态可映射为暂不可操作。`connected` 只说明授权连接；`read_active`/`write_active` 说明当前资格；`synced` 说明收到本次约定的写入回执，各自不要混用。

刷新结果未知且无法确认整条远程授权已撤销时，另保留 `revocation_unconfirmed`；界面明确本应用已停用、远程撤授权仍待确认。不要把这种状态渲染为“全部撤销成功”。

后端的 OAuth 错误不能伪装成本应用登录失效：例如用业务错误码/409 提示重新连接 EverMe，只有自己的登录凭据失效才触发 APK 登出。生产与测试环境由可信服务器配置选择，不由请求体传入任意环境。

## APK 授权界面

1. 披露哪些数据会发送给 EverMe，以及相关片段是否进入另一个模型；连接操作不能默默打开独立的数据共享许可。
2. 通过业务 API 申请 URL，按已验证 discovery 的 HTTPS host、port、path 校验；拒绝 userinfo、fragment、控制字符和未许可重定向。不要把 APK 登录 token 追加到浏览器 URL。
3. 通过系统浏览器或 Custom Tabs 打开；此步骤只代表浏览器已打开。
4. `onResume` 后用发起操作时的账号会话重新查状态；返回深链只是刷新提示，不相信深链里的 `connected=true`。
5. 页面异步回调须检查 owner 和本地 session generation；换号、退出或页面销毁后丢弃旧响应。缺字段/离线时显示待确认，不默认成功。

以下是与框架无关的伪代码，需要接到实际 API、生命周期和主线程：

```text
ticket = snapshot(currentOwner, loginGeneration)
result = backend.authorize(disclosureVersion)
if ticket != currentLoginSnapshot(): discard result
validateAuthorizationUrl(result.url)
openSystemBrowser(result.url)

onResume:
    status = backend.status(forOwner = ticket.owner)
    if ticket == currentLoginSnapshot(): render(status)
```

## 服务端隔离与队列

建议最小记录：

| 记录 | 关键字段 |
|---|---|
| OAuth client | 环境、issuer、client_id、精确 callback、registration 状态 |
| Connection | owner、client、authorization_id、revision、加密 grant、有效期、状态 |
| Attempt | state 摘要、owner、授权代次、加密 verifier、失效时间、一次性 claim 状态 |
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

日志仅保留必要 request ID、阶段、耗时、状态和脱敏错误码。不要写入 token、verifier、code、state、Authorization、记忆正文、查询全文、用户对话或可泄露秘密的完整 URL。网络读取设截止预算；超时保留同 owner 的本地能力，不阻塞眼镜的正常运动流程。
