# 掘金浏览器工作流

## 适用范围与证据

以下是 2026-09-05 在掘金 Markdown 编辑器完成一次真实图文发布所确认的操作经验，不是平台永不变更的 API 合约。曾成功通过原生图片工具上传多张本地图片、粘贴 Markdown、填写分类/标签/摘要/封面，并观察发布成功、审核中及后续正式文章页。该经验不授予未来发布权限。

## 进入正确编辑器

优先使用首页“创作者中心”旁的下拉菜单 → “写文章”，或创作者中心的文章管理与写文章按钮。只编辑用户指定的旧文章，或在明确要求新发时创建草稿。

已观察的“写文章”入口使用 `/editor/drafts/new?v=2`。不要把它误写成 `/editor/drafts/new/v2`：后者曾回到首页。仍应以当前 UI 导航为主，不循环猜路由。窄窗口可能隐藏创作入口；先尝试响应式菜单，确实需要桌面入口时才临时调整视窗，结束后恢复。

若按钮没有响应，检查是否有菜单遮挡、页面新开标签或文件选择器；重新读取状态后再选择替代入口。角色/文字定位匹配多个元素时缩小到当前面板，不盲用第一个文本匹配。不要读取网站隐藏内部状态、Cookie 或私有接口来绕开 UI。

## 上传正文图片

工具栏的图片图标会打开文件选择器，不一定先显示对话框。使用当前宿主文档规定的流程：先等待 `filechooser`，再点击已观察到的图片控件，最后 `setFiles`；多选前检查 `isMultiple()`。

曾观察到工具栏左右两侧存在同名 `bytemd-tippy-path`。图片按钮在左侧工具栏；未经本轮 DOM 核实，不能照抄这个选择器。封面选择器与正文图片选择器是两个不同控件。

首次上传前保存正文基线。如果上传器会把图片标记插到光标位置，可在同一草稿的临时图片区收集全部托管映射；随后用已验证的完整 Markdown 替换临时区。替换之前必须备份和核对任何用户手动改动。不要把临时图片堆留在正文开头。

图片链接从上传结果中的实际 Markdown 或预览 `<img>` 读取。批量上传文件名使用内容哈希可避免同名覆盖。异步顺序、相同尺寸或“共 29 张”都不能证明对应关系正确。

### 宿主提供 Playwright 风格接口时的参考

必须先阅读当前浏览器工具文档；接口不同就使用其支持的等价方式。`imageButton` 是本轮 DOM 中已唯一定位的图片控件，不是凭空创建的变量。

```javascript
const pending = tab.playwright.waitForEvent('filechooser', { timeoutMs: 60000 });
await imageButton.click();
const chooser = await pending;
// absoluteFiles 仅包含本次文章清单内、明确获准上传的本地图片。
if (absoluteFiles.length > 1 && !(await chooser.isMultiple())) {
  throw new Error('请按单图上传流程处理');
}
await chooser.setFiles(absoluteFiles);
```

下面是只读采集思路。选择器需本轮核实，并且应保存完整结果到当前任务的临时工作数据，不把签名地址打印到分享说明。

```javascript
const observed = await tab.playwright.evaluate(() =>
  Array.from(document.querySelectorAll('.bytemd-preview img')).map(e => ({
    uploaded_name: e.alt,
    url: e.src,
    loaded: e.complete && e.naturalWidth > 0,
    width: e.naturalWidth,
    height: e.naturalHeight
  }))
);
```

`alt` 只有在本次上传结果确实保留了文件名时才能用作文件名映射。若无法明确映射，改为更小批次或逐张上传，不能猜测。

## 粘贴和预览

掘金 Markdown 区使用编辑器管理内容。不要用 `evaluate` 赋值 textarea、调用编辑器隐藏方法或派发事件。通过正常粘贴或工具明确支持的编辑动作写入。

某些 CodeMirror 隐藏 textarea 的 `value` 是旧输入缓存，不代表完整文稿。以实际编辑器可见内容、Markdown 预览和保存状态综合核对。不要因为这个缓存而重发稿件。

TXT 转义后也是 Markdown 发布稿；无图稿正常发布，不强制生成插图。代码块语言标签可能作为 `pre` 内工具栏文字出现，因此比较 `pre code` 正文，不比较整个 `pre.textContent`，否则会误判多了 `bash`、`json` 等文字。

## 发布设置与恢复

按文章主题选最贴切的分类，选少量相关标签，摘要保留核心读者、内容与收获。封面用用户提供或文章中适合的授权图片；不擅自生成、改绘或裁切重要内容。

点击“确定并发布”后读取成功/失败消息及实际文章页。若网络断开或操作超时，先查已发布文章和原草稿，再决定是否重试。出现“审核中”就记录审核中，不为催审反复提交。

已观察到 `/spost/<id>` 可能随后跳转至 `/post/<id>`。这不是可直接替换字符串的通用规则；打开文章并记录真实跳转结果。用同一个登录态能看见文章，不足以证明所有访客都可见；如果未做未登录核验，交付时不声称已完成匿名访问验证。
