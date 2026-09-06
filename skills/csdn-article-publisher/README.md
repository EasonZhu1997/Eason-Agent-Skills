# CSDN 图文发布与图片修复技能 · 分享说明

这个技能帮助 AI 助手把 Word、TXT、MD / Markdown 文章上传到 CSDN，并修复缺图、重复图、错位图和图片转存失败。重点是保留原文、格式及图片位置，并分清草稿、审核和真正公开的状态。

用户明确选择时，还可优先通过 **CSDN 官方同步助手** 将同一篇文章同步到掘金、知乎，再逐个平台校对。同步通常先生成目标草稿，不等于正式发布；详见 [多平台同步说明](references/cross-platform-sync.md)。

## 怎么分享

直接发送整个 `csdn-article-publisher` 文件夹或外层 ZIP，**不要只复制 SKILL.md**。`references/` 中的引用说明和 `scripts/` 中的工具已经随包提供，不依赖原作者的文章、电脑路径或临时目录。

包内没有原文章、用户图片、账号密码、Cookie、Token、真实已发布文章 ID 或用户上传记录。使用时产生的文章备份和 URL 清单属于使用者自己的任务数据，请勿再混入技能公开分享。

## 怎么使用

1. 解压，保持文件夹结构不变。
2. 放到你的 AI 客户端支持的技能目录。当前 Codex 的个人技能可放进 `~/.agents/skills/`，项目技能可放进项目内的 `.agents/skills/`。旧版或自定义环境以实际技能发现目录为准；先检查同名技能并备份比较，不要直接覆盖或在多个目录重复安装。其他客户端按其技能导入方式操作，参见 [官方技能说明](https://learn.chatgpt.com/docs/build-skills)。
3. 在会话中确认技能可用；若当前会话尚未发现新技能，开启新会话再试。
4. 提供文章文件、目标 CSDN 账号/已有文章链接，以及“仅保存草稿”或“提交发布”。浏览器须具备相应操作能力，并已登录目标账号。

可直接复制的指令：

> 使用 $csdn-article-publisher，把我提供的 Word 上传到 CSDN，保留标题、正文和所有图片。先保存草稿，核对每张图的位置，不要直接发布。

> 使用 $csdn-article-publisher，把这份 TXT 原样保存为 CSDN 草稿。保留缩进、连续空格和首尾空行，不把里面的 Markdown 示例变成排版。

> 使用 $csdn-article-publisher，把这份 MD 和同目录 images 文件夹上传到 CSDN。保留标题、代码、列表和配图位置；先确认当前是 Markdown 还是富文本编辑器，再采用对应路线，检查后保存草稿。

> 使用 $csdn-article-publisher，修复这篇已有 CSDN 文章。以我指定的 Word 为准，只调整缺失和错位的图片，其他文字不要改；检查通过后提交更新。

> 使用 $csdn-article-publisher，将这篇已确认的 CSDN 文章通过官方同步助手同步到掘金和知乎。检查两边的图片和排版，先只保存草稿，不要正式发布。

> 使用 $csdn-article-publisher，把这篇文章发布到 CSDN，并同步到掘金、知乎；三边检查后都正式发布。若某个平台已经有对应文章，更新原帖，不要重复新建。

## 多平台同步的条件

这是“CSDN 技能 + 官方浏览器同步助手”的可选路线，不是技能自带登录或发布接口。先检查支持扩展的浏览器、助手状态及同一浏览器内的目标账号登录；没有这些条件时不能声称一键同步可用，也不自动安装扩展或读取 Cookie。官方资料与操作入口见 [同步说明](references/cross-platform-sync.md#官方能力与前提)。

官方同步后逐站检查草稿。确需分平台补发/修复时，优先使用当前环境已可用的掘金、知乎技能；它们不是本 ZIP 的必需依赖。只授权 CSDN 就只发 CSDN，不默认多平台公开发布。同步的一站失败，不重复执行已成功站点，也不将未知状态直接当作失败重发。

## 三种输入怎么处理

- **TXT**：默认严格读取原文，支持 UTF-8 / BOM 和显式指定 GB18030 等编码；`render_richtext.py --literal-txt` 保留全部字面文字和空白，不把图片写法自动变成图。TXT 确实采用 Markdown 语法时才加 `--txt-as-markdown`。
- **MD / Markdown**：保留标题、段落、列表、代码与链接，按图片原位置提取安全的本地图并生成独立 `CS_IMAGE` 占位。上传后校验原图指纹及正文基线、原位回填。缺图、外链图、路径越界和不可靠语法会明确暂停，不静默丢图。
- **Word**：原图与上下文提取及 HTML 图片修复流程保持不变。Word 清单不是完整正文转换；新文章需宿主可靠 DOCX 转换能力或用户提供的对应导出稿，不能宣称本包自带一键完整排版转换。

当前页面确实提供 Markdown 源码编辑时，才直接粘贴回填后的 Markdown；富文本编辑器先生成语义 HTML，再使用真正的富文本粘贴。纯 TXT 默认用富文本预格式路线；若当前 Markdown 编辑器无法保留原空白，不直接贴入并声称保真，应使用可验证的原生预格式块、用户同意的富文本入口或停在本地稿。

Word 的数字编号清单、Markdown 的 `CS_IMAGE` 清单、富文本验收清单分别保存，不能交叉传给不同脚本。TXT/MD 的详细操作见 [输入说明](references/text-input.md)、[图片回填](references/md-image-mapping.md)、[富文本处理](references/richtext.md)。

## 运行环境

- Word 图片清单、TXT/MD 预处理、图片回填、纯 TXT 保真：Python 3.9+，仅标准库。
- Markdown 转富文本：额外需要 `markdown-it-py==3.0.0`，见 `requirements-render.txt`。在允许安装依赖的独立虚拟环境内安装，不修改用户全局环境。纯 TXT 路线不需要它。
- 本地 HTML 图片归位脚本：Node.js 18+，仅内置模块。
- 网站操作：需要宿主提供可用的浏览器/电脑操作工具。这个技能本身不是浏览器插件，也不会携带登录会话。
- 没有浏览器工具时，可整理本地上传材料，但不能自动完成网站操作。遇到锁屏或验证环节，仍需用户接手。

## 文件一览

- `SKILL.md`：AI 助手的任务入口和边界。
- `agents/openai.yaml`：技能显示名称与示例调用。
- `references/`：浏览器操作经验、图片位置数据格式、发布验证清单。
- `scripts/docx_inventory.py`：提取 Word 原图及上下文。
- `scripts/repair_html.mjs`：在本地把已经上传的图片 URL 放回正确图注位置。
- `scripts/prepare_text.py`：TXT/MD 安全预处理、本地图清单与占位。
- `scripts/finalize_images.py`：验证正文和原图指纹，将实际上传地址回填到 Markdown 原位置。
- `scripts/render_richtext.py`：纯 TXT 保真，或将最终 Markdown 转成可核对的语义 HTML。
- `requirements-render.txt`：仅 Markdown 富文本路线的可安装依赖声明，不是已打包的 Python 运行环境。
- `scripts/test_*.py`、`scripts/test_*.mjs`：可运行的本地测试，不访问网站。

网页控件会变化。说明中的按钮名称只是操作线索；例如批次大小经验不是平台承诺。技能不能保证自动通过审核，也不会跳过验证码或网站限制。

## 自检

在技能文件夹内运行以下命令，只会使用临时合成数据，不访问 CSDN：

```bash
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
node scripts/test_repair_html.mjs
```

完整的 Markdown 实际渲染测试需安装 `requirements-render.txt`；HTML5 纯 TXT 首换行/字符保真测试另需可选测试依赖 `html5lib==1.1`。缺依赖会跳过对应项，不能把跳过汇报为已通过。测试只处理临时合成稿，不登录、不上传、不发帖。
