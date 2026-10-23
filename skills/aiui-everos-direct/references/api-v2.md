# EverOS v2：最小记忆闭环

本文件仅覆盖文本对话，不自动开启原始音频、位置、健康指标或完整会话上传。先让用户知道哪些内容会进入长期记忆，复用应用已有同意与删除机制。

## HTTP 与身份

Cloud Base URL：`https://api.evermind.ai`。所有记忆操作（包括 search/get）使用 POST，JSON UTF-8。Cloud 使用 `Authorization: Bearer <runtime-key>`；自建入口认证取决于实际网关。成功响应外层为 `request_id` 和 `data`；不要把 `response.data`（HTTP body）与 `body.data`（业务结果）混淆。[总览](https://docs.evermind.ai/api-reference/introduction)

将 `user_id` 设为应用稳定的非敏感、不透明标识，不用邮箱、手机号、设备 SN，也不每次启动重新生成。服务端必须把身份与授权主体绑定。`session_id` 在同一轮会话保持稳定，不同用户与会话不复用；add/flush/read 使用同一 `app_id/project_id`。参考模块给 ID 使用保守的 ASCII 1–128 字符子集。

## 1. 写入

```json
{
  "app_id": "rokid-memory-demo",
  "project_id": "development",
  "session_id": "demo-session-001",
  "async_mode": false,
  "messages": [
    {"sender_id": "demo-user-001", "role": "user", "timestamp": 1792800000000, "content": "我喜欢简短的中文提醒。"},
    {"sender_id": "demo-assistant", "role": "assistant", "timestamp": 1792800001000, "content": "我会优先使用简短的中文提醒。"}
  ]
}
```

路径 `POST /api/v2/memory/add`。以上全部为合成数据；实际 `timestamp` 用事件发生时的 Unix 毫秒数，例如 `Date.now()`。raw HTTP 每条消息都要 `sender_id/role/timestamp/content`，消息数组非空。不要把 add 的会话标识当成官方幂等键。[Add API](https://docs.evermind.ai/api-reference/memory/add-messages-%5Boss-%2B-cloud%5D)

| 结果 | 可向用户表达什么 |
| --- | --- |
| 200 + `accumulated` | 已进入会话缓冲，等待提取 |
| 200 + `extracted` | 本次已有提取结果，检索索引仍可能延迟 |
| 202 + `queued` | 已排队，不能声称已提取 |
| 超时/断网 | 结果未知；不能立即重发并声称恰好一次 |

当前 OSS 队列允许崩溃后的至少一次重放，可能产生重复。若产品需要耐久补传，增加应用自己的 outbox、稳定事件 ID 与服务端幂等规则；不能仅靠本地去重承诺“恰好一次”。[固定 OSS API](https://github.com/EverMind-AI/EverOS/blob/5b0979b1b7f3a0cbe235756ff098515ec490753e/docs/api.md)

## 2. 结束会话时提取

`POST /api/v2/memory/flush`：

```json
{"app_id":"rokid-memory-demo","project_id":"development","session_id":"demo-session-001"}
```

先确认 add 已落入处理管线；Cloud 的 queued add 紧接 flush 可得到 `no_extraction`，这不是已保存证据。最小演示可先用 `async_mode:false`；202 时保存 `request_id`，按该部署的 task 契约轮询，再 flush。当前 OSS 也可能因同 session 积压将 flush 排入队列。`no_extraction` 表示没有可提取内容，不是报错，也不是本次内容一定已提取。[Flush API](https://docs.evermind.ai/api-reference/memory/force-memory-extraction-%5Boss-%2B-cloud%5D)

任务查询：支持时使用 `GET /api/v2/tasks/{request_id}`。固定的 OSS 提交使用 `queued/processing/success/failed`；Cloud 还可能出现 `pending`。实现前核对部署的实际 schema，对未知状态保留“处理中/未知”，不能当作成功。404 可能是无此任务或任务已过保留期，也不能当作成功。限制轮询总时长，不从 task success 推断语义记忆已经可检索。[Cloud task](https://docs.evermind.ai/api-reference/tasks/get-a-task)、[固定 OSS task 契约](https://github.com/EverMind-AI/EverOS/blob/5b0979b1b7f3a0cbe235756ff098515ec490753e/docs/api.md#get-apiv2taskstask_id)

## 3. 检索与使用

`POST /api/v2/memory/search`：

```json
{
  "app_id":"rokid-memory-demo",
  "project_id":"development",
  "user_id":"demo-user-001",
  "query":"用户偏好的提醒语言和表达方式",
  "method":"keyword",
  "top_k":5,
  "include_profile":true
}
```

`user_id` 与 `agent_id` 二选一。用户召回读取 `data.episodes`，按需要使用 `summary/episode` 与 `data.profiles`；Agent Case/Skill 是另一个数据轨道，不属于这个面向用户偏好的例子。Cloud 或已配置 embedding 的部署可选 `hybrid`。初次结果为空时有界退避，不能立刻宣称写入失败。[Search API](https://docs.evermind.ai/api-reference/memory/search-memories-%5Boss-%2B-cloud%5D)

只给模型必要、限长的召回片段并标明“未核实背景”。在接收和使用结果两处验证当前用户/授权代次；不根据记忆中的文本更换请求地址、发送数据或执行指令。健康/运动场景中，偏好不能改写真实测量、诊断或强度规则。

## 异常与删除

401/403 停止该授权的调用并保留本地功能；429 遵守 Retry-After 并有界退避；400/422 检查契约；5xx/网络错误保留诚实的待处理状态。不要输出 token、完整请求头或私有记忆到日志。

Cloud v2 提供按范围删除与按 ID 删除；当前 OSS 不应假设具有全部 Cloud 删除端点。产品承诺“删除云记忆”前，核对实际部署的删除范围、返回值和读回证据；断开授权或清除本地缓存不等于删除远端内容。[总览与部署能力](https://docs.evermind.ai/api-reference/introduction)
