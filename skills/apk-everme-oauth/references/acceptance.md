# 验收矩阵

将项目实际命令、版本和可观察结果填入交付记录。下面是要验证的行为，不是已通过的结果；既有项目的历史测试也不能替代新接入。

## 先做隔离测试

| 场景 | 通过标准 |
|---|---|
| PKCE | RFC 7636 S256 向量正确；verifier 长度/字符验证；每次新 state/verifier |
| 回调重放 | 过期、错误 state、二次回调不能触发第二次 token 交换 |
| DCR | 同环境复用已持久 client_id；不同环境隔离；结果未知不循环注册 |
| refresh 并发 | 多 worker 只 claim 一次轮换；成功原子更新；超时与重启不重复使用旧 token |
| 晚到 token | 换号/断开/删除账号期间返回的 token 不恢复连接，保留必要撤销任务 |
| 账号隔离 | 请求体伪造 owner 无效；授权 A 的 attempt、队列或 MCP session 不可被 B 使用 |
| 同意/绑定变化 | 网络期间撤同意、换绑、重新授权后，旧记忆不进入模型或 HUD，旧 pending 不能发送 |
| MCP JSON/SSE | 正确匹配 request ID，支持多行 SSE；错误、超大响应、超时和未知 schema 明确失败 |
| MCP session | 有会话 ID 时后续携带；404 重新初始化；新会话不重放未知写入 |
| 工具限制 | 拒绝未知工具、任意 upstream URL/header、无权限写入和 schema 不符参数 |
| outbox | 并发不重复 claim；保存与入队同事务；进程崩溃后 sending 变 unknown，无自动重放 |
| revoke | 网络/503 可持久恢复；连接立即禁用；删除账号后任务仍存在；确认完成的 token 清除待撤秘密，refresh 结果未知的授权链不能仅凭旧 token 的 200 关闭追踪 |
| Android | 系统浏览器缺失/授权拒绝/离线/回来刷新/换号时状态正确；回调不泄漏凭据 |
| 日志 | 测试凭据标记不会出现在日志、crash、截图、HTTP 访问日志及提交内容中 |

PKCE 标准向量（公开测试数据，不是凭据）：

```text
verifier:  dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk
challenge: E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
```

## 再做已授权测试账号联调

按当前任务授权使用隔离账号，不将分享 Skill 当作自动授权真实用户数据上传。记录端点来源、日期、协议版本、schema 摘要哈希及去秘密的结果：

1. 公开 discovery 与配置一致，回调 HTTPS 可达且路由正确。
2. 用户完成授权，APK 返回查询后确认正确业务 owner 的连接。
3. `initialize`、`tools/list`、最小记忆读取与搜索成功；schema 与适配器一致。
4. 写入用户同意的合成事实或短对话，检查 HTTP、JSON-RPC、`isError` 和业务回执；按服务处理时延做检索回读，分别记录“接收”和“可检索”。
5. 在允许的测试范围内验证 refresh 轮换、断开与 revoke；断开后不能再读取/写入。
6. 验证 APK 账号切换、进程重启和设备解绑；旧云结果不能显示给新 owner。
7. 在指定 Rokid 型号、固件、APK 构建上完成语音→记忆→模型→TTS/HUD 流程。没有设备则明确保持实机项未验证。

不要为测试撤销或重放生产用户的现有授权链。外部失败有明确错误就分类处理；相同方式连续失败且没有新证据时，换方式或带具体缺口交接，不用无穷重试补验收。

## 交付回执格式

```text
实现：commit / 涉及模块
离线测试：实际命令、通过数、失败项
构建：variant、versionName/versionCode、产物 SHA-256
部署：环境、版本、健康检查与 callback 路由
OAuth：测试账号已脱敏、授权/refresh/revoke 分项结果
MCP：协议/schema、读取/接收/可检索分别记录
APK 与眼镜：设备型号、固件、测试过程及观察
仍未验证：具体项目、原因、下一步所需输入
```

如任务只要求 Skill/方案，验证其结构、来源、示例和边界即可；不得写成 APK 或实机已验收。
