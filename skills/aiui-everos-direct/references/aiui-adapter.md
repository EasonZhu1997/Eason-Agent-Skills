# AIUI 网络、存储与生命周期适配

## 网络契约

使用 `import wx from 'wx'`，不是命名导入。参考模块通过 `request: options => wx.request(options)` 注入调用。AIUI 的 wx API 名称类似小程序，但不能推断完整微信或浏览器行为。

已核对的请求字段：`url/method/header/data/dataType/responseType/timeout/success/fail`；返回 `RequestTask`。JSON 请求显式写 `dataType:'json', responseType:'text'`，因为默认 responseType 是 ArrayBuffer。`success` 只表示收到 HTTP 响应，仍要检查 `statusCode`。文本 JSON 或旧宿主 ArrayBuffer 需要防御性解析。[官方 wx 文档](https://github.com/yodaos-project/AIUI/blob/a27bb7a83f0e31a9749ba451ddf5c8686131a3df/skills/aiui-dev/references/apis/wx.md)

Page 可按目标版本使用 `fetch`，但现有应用已用 wx 时保留其错误/取消处理。不要把 Page 的 fetch 代码直接搬到 Agent Worker；Worker 的全局能力与生命周期不同。

## SDK 的接线方式

将整个包内 `sdk/` 复制到应用 `lib/everos-sdk/`，保留 `package.json` 的版本和 LICENSE。SDK 是唯一 HTTP 实现；应用只接入自己的凭据、身份与生命周期。`createAIUIEverosClient` 负责绑定 `wx.request`，不用另写请求封装。需要自定义传输时才使用底层 `createEverosClient`。

以下是接线片段，`sessionConfig` 与 `authorization` 由应用自己取得，**不是完整可运行 Page**：

```js
import wx from 'wx';
import { createAIUIEverosClient } from '../../lib/everos-sdk/index.js';

const client = createAIUIEverosClient({
  wx,
  baseUrl: 'https://api.evermind.ai',
  scope: sessionConfig, // {appId, projectId, userId, assistantId}
  getAuthorization: () => authorization, // 运行时字符串，例如 Bearer + 自己的 key
  isCurrent: () => currentOwnerGeneration === frozenOwnerGeneration,
});

const result = await client.search({query: '偏好的提醒方式', method: 'keyword'});
// result.data 是业务 data；真正展示或传给模型前，再检查页面和 owner 仍有效。

// 所属页面销毁、账号切换或撤权时：
client.dispose();
```

`dispose()` 后重新进入需要新实例；不要反复复用已销毁的 client。Page 的最终清理放在 `onUnload()`，Widget 放在 `onDestroy()`；hide/detach 暂停可见任务并使对应 UI 请求代次失效，恢复时按业务需要重建。取消在途请求只能尽力停止传输，不能保证已发出的写入没有在服务端执行。

首次集成先只接用户触发的“保存此偏好/读取记忆”，再按产品已授权范围扩展自动保存。不要把示例中的合成测试数据在启动时自动写入用户账号。

适配器对原始文本/字节和宿主已解析的 JSON 都做大小检查，并限制对象节点与嵌套深度。429/503 错误可携带经过解析的 `error.retryAfterMs`，接受整数秒或标准 IMF-fixdate 日期，不会返回整个响应头；调用方只在已确认可以重试的读取或未接受操作上使用它。等待时间超过本次预算时结束本次尝试，不缩短服务器指定间隔，也不因此重发结果未知的写入。缺少、无效或未支持的旧式 Retry-After 日期不触发自动重试，由应用决定保守退避或结束本次尝试。

## 凭据与存储

`wx.setStorageSync/getStorageSync` 支持 JSON 数据，但没有在此契约中承诺硬件加密的密钥库。不能因为可存储就将共享主 key 写进 AIX、代码、二维码、日志或普通缓存。参考适配器仅从运行时回调取认证，不负责存储。

可缓存本地业务记录与 outbox，但按当前用户/授权代次分区；写后读回再确认落盘。存储抛错、读回不一致或序列化失败时保留未确认状态。用户切换后清理其缓存/在途引用并隔离旧队列，不能拿新用户 token 重放旧内容。无需为了接入本 Skill 清空整个应用 storage。[官方 storage 行为](https://github.com/yodaos-project/AIUI/blob/a27bb7a83f0e31a9749ba451ddf5c8686131a3df/skills/aiui-dev/references/apis/wx.md)

## 生命周期与配置

- Page 使用 `export default { ... }` 和 `this.setData()`；`.ink` 采用 `<script def>/<script setup>/<page>/<style>`，不要生成 `Page({...})`。
- 在页面 hide/unload、身份变更、撤权时使当前请求代次失效；尽力 abort，但仍处理迟到回包。关键 UI 不等待长期提取或云请求结束。
- 当前官方 `app.json.permissions` 文档列出 `GEOLOCATION/CAMERA/RECORD_AUDIO`，区分大小写。不要因旧项目 AGENTS 中写有 network 就机械添加一个未经当前 schema 确认的 `"network"` 权限；按实际宿主文档声明需要的能力。
- 不为了接 HTTPS 自动申请麦克风、定位或相机权限。工程的 engine 范围与目标宿主、构建器分别验证，不复制参考项目的版本范围。

来源：[官方 AIUI framework](https://github.com/yodaos-project/AIUI/blob/a27bb7a83f0e31a9749ba451ddf5c8686131a3df/skills/aiui-dev/references/framework.md)、[Web API](https://github.com/yodaos-project/AIUI/blob/a27bb7a83f0e31a9749ba451ddf5c8686131a3df/skills/aiui-dev/references/apis/web.md)。
