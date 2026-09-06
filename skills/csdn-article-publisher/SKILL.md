---
name: csdn-article-publisher
description: "Upload or update Word, TXT and Markdown articles in CSDN using an authorized browser, preserving text, formatting and image positions; repair missing or failed-transfer images and verify draft, review and public states. Use for CSDN article publishing and image-placement repair, not general copywriting or other publishing platforms."
---

# CSDN 图文发布与图片修复

把用户指定的 Word、TXT、MD / Markdown 文章上传到 CSDN，或修复已有文章的图片。成功标准是内容、图片位置和保存状态均可验证，不是仅点过发布按钮。

## 先确定这次任务

- 明确源文件/正文、目标账号和文章、新建还是更新，以及只存草稿还是发布。缺失且无法从当前请求确定时才询问。
- 用户指定原帖或编辑器链接时，更新同一文章，保留标题和无关编辑，不重复新建。
- 只要求图片修复时，不顺手改文案、图片内容、风格、许可或其他平台。原图发现问题可单独说明。
- 本技能不授予登录、发帖、权限变更或跨平台同步的新授权。执行当前用户实际要求的范围，遵循宿主的确认规则。
- 只读请求只检查；“整理成技能”只制作技能，不顺带发布文章。

## 工具和资料入口

使用当前环境实际提供的浏览器工具；先读它的操作说明，以当前网页控件为依据。不要把本包的例子当成某个客户端固定可用的 API。

- 浏览器录入、上传、光标和故障恢复：读 [references/browser-workflow.md](references/browser-workflow.md)。
- Word 原图清单、已上传 URL 清单与本地归位：读 [references/image-mapping.md](references/image-mapping.md)。
- TXT / Markdown 准备、编码和本地图：读 [references/text-input.md](references/text-input.md)。
- Markdown 图片原位回填：读 [references/md-image-mapping.md](references/md-image-mapping.md)。
- 纯 TXT 保真和 Markdown 转富文本：读 [references/richtext.md](references/richtext.md)。
- 保存、审核、公开状态和结束前检查：读 [references/verification.md](references/verification.md)。

所有脚本和引用均在本文件夹内。脚本只处理本地文件，不读取浏览器凭据、不调用 CSDN 私有接口、不执行发布。

## 按来源和当前编辑器选择路线

- **普通 TXT**：默认运行 `render_richtext.py --literal-txt` 读取原 TXT，保留字面符号、缩进、连续空格和首尾空行，再走富文本或原生预格式块转入。不要把 `#`、图片写法或反引号自动当排版；仅当用户确认 TXT 本来就是 Markdown，才使用 `prepare_text.py --txt-as-markdown`。
- **MD / Markdown**：先 `prepare_text.py`，解决缺图和其他阻断；通过原生界面上传清单中的本地图，再用 `finalize_images.py` 回填 `CS_IMAGE` 占位。零图稿同样可通过空映射 `{}` 完成本地校验。
- **当前确实为 Markdown 编辑器**：把最终 Markdown 作为源码粘贴到其源码区，并检查预览中的标题、代码、列表、链接和图片；不是把源码粘贴到普通富文本正文。
- **当前为富文本编辑器**：用 `render_richtext.py --article` 生成语义 HTML，再通过工具实际支持的 HTML 剪贴板或原生复制粘贴转入，详见富文本说明。只生成 HTML 不代表网站已收录格式。
- **Word 或已有帖图片修复**：保留下面的 Word 清单与 `repair_html.mjs` 路线。本包不是完整 DOCX 排版转换器；新 Word 正文需宿主可靠转换或用户导出，再逐项核对。

两种图片清单不能混用：`docx_inventory.py` 的 Word 清单配数字键 URL 映射，交给 `repair_html.mjs`；`prepare_text.py` 的 Markdown 清单配 `{{CS_IMAGE_0001}}` 对象映射，交给 `finalize_images.py`。转换生成的富文本清单又是验收基线，不是图片回填输入。工作输出分目录保存，不覆盖用户源文件。

## 执行流程

### 1. 取证和备份

读取最新指定源文件，不沿用旧文章的图片总数。TXT / MD 按上方对应路线准备；对 Word 用随包脚本生成有序清单：

```bash
python3 scripts/docx_inventory.py --source "/path/to/article.docx" --out "/path/to/new-task-output"
```

检查原图、相邻段落和图注。重复使用同一图应保留每次出现；损坏引用、浮动图、无图注或表格里的图需人工核对，不能直接猜位置。

更新已有文章前，通过允许的只读 DOM/编辑器导出能力记录原正文、标题、图片清单和文章 URL，保存到本次任务工作目录。**修复脚本的输入应是插入任何临时编号之前的备份**，不是已经混入上传测试内容的正文。

### 2. 形成明确的图片位置表

每次图片出现都绑定编号、原文件、图注/上下文锚点、最终平台地址。

- Markdown 依据原文每次图片出现的 `CS_IMAGE` 位置回填，保留 alt 和支持的 title，不需虚构图注。以下图注锚点规则用于 Word / 现有 HTML 修复。
- 有唯一图注：通常放在图注前，但仍以 Word 原文关系为准。
- 封面、无图注、同段多图、重复图注：看前后文或 Word 版面，提供明确锚点。
- 不能唯一定位时停止自动归位，先确认位置；不要把未定位的图统一堆在开头或末尾。

### 3. 上传原图

优先使用 CSDN 当前的本地图片上传入口。先用一张图验证实际文件上传、托管地址和加载结果，再扩大到小批次。

若当前富文本编辑器支持粘贴内嵌原图并自动转存，可以分批使用；必须逐批确认真实托管地址。不要留下 `file:`、WPS 临时路径、`blob:` 或仅在本机有效的图片。

不要把一次失败推断成固定平台限制：批量能力、文件限制、编辑器结构以当前页面为准。整篇内嵌大图可能使传输中断，出现问题时缩小批次或换回原生文件上传，而不是原样重复。

### 4. 归位并保留原文

少量缺图：在经过验证的光标处逐张补图。

Word / 现有 HTML 大量缺图或错位：上传齐全后，用 [scripts/repair_html.mjs](scripts/repair_html.mjs) 在本地对原正文备份生成归位版本。Markdown 用 `finalize_images.py`，不能把其清单传给 Word 修复器。先核对输出审计，再通过当前编辑器支持的正常粘贴/导入动作写回。不能通过只读页面求值接口修改 DOM、调用隐藏编辑器对象或绕过界面提交。

新文章可用宿主现有的可靠 Word→富文本转换能力；本包的提取脚本不是完整 Word 排版转换器。保留代码换行、链接和标题层级，不能把 HTML 源码当正文直接贴入。

### 5. 验证后保存

按 [references/verification.md](references/verification.md) 检查图片数量、顺序、原图对应、图注位置、加载和正文保留，再执行用户授权的保存/发布。

分别报告“编辑器已核对”“已保存草稿”“已提交审核”“公开页已验证”。审核未结束时不能声称已经公开完成；公开页打不开时如实说明。

## 中断和交接

锁屏、验证码、登录失效或工具断连时，先保存允许保存的任务记录，再请求必要的用户接手。不要通过其他技术绕过浏览器或系统的安全限制。

遇到无变化/失败，先检查是否已成功、选区是否正确、是否有弹窗。查明原因后最多再试两次同类操作；仍失败则换已经支持的安全方式或报告具体阻碍。发布响应不确定时先查同一篇文章状态，避免重复发帖。

交接记录写在任务工作目录，而不是本技能文件夹：源文件指纹、文章链接、成功图片 URL、缺失项、当前位置、最后确认状态、后续动作。共享技能时不要打包这些用户数据。
