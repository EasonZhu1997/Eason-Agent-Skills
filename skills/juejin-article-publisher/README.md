# 掘金图文发布技能 · 分享包

把文章交给 AI 助手，按原文标题和配图位置整理到掘金。支持新发、修改指定文章、只存草稿、修复图片/排版；**不是双击后自动登录发布的软件**。

## 支持什么文件

| 来源 | 处理方式 |
| --- | --- |
| TXT | 默认保留纯文本和换行，转义 Markdown 特殊字符；UTF-8/BOM、UTF-16 BOM，其他编码显式指定 |
| MD / Markdown | 保留正文结构和代码，清点常见行内/引用图片，提取本地图片并生成回填占位 |
| Word DOCX | 内置安全提图与位置清单；配合已有 Markdown 导出稿或已安装文档转换器进入同一发布流程 |

纯文字文章也支持，不会强制配图。图片缺失、复杂 HTML 图片语法、网络图或越界路径会明确提示处理，不会自动下载或静默跳过。

Word 的浮动图、文本框、特殊代码样式需要核对；不保证像素级复制 Word 版式。完整 Word 转换需要已有转换器或经确认的 Markdown 中间稿，详见 `references/word-input.md`。

## 怎么分享与使用

把整个 `juejin-article-publisher` 文件夹或配套 ZIP 发给对方，**不要只发 SKILL.md**。脚本和引用说明均已在包内，不依赖本机文章目录。

对方需要一个支持技能的 AI 助手、可用的浏览器交互工具及掘金账号。登录和验证码按其宿主要求由用户处理；包内不含账号、Cookie、API key，也不自动安装浏览器插件。

可以把解压后的技能目录直接交给助手：

> 使用这个目录里的 SKILL.md，把我提供的文章发布到掘金；保留标题和图片位置，发布后检查结果。

需要本地自动发现时，将该文件夹放入当前 Codex 支持的技能目录。官方目前列出的个人目录为 `~/.agents/skills/`，项目目录为 `.agents/skills/`；旧版本以其实际技能目录为准，避免同名重复安装。解压到桌面不等于已经安装。参见 [OpenAI 官方技能说明](https://learn.chatgpt.com/docs/build-skills#where-to-save-skills)。

安装后可这样说：

```text
使用 $juejin-article-publisher，把附件 article.txt 整理到掘金草稿，先不要发布。
```

```text
使用 $juejin-article-publisher，把 article.md 和同目录 images 文件夹里的配图发布到掘金。标题保持原样，上传图片并检查顺序。
```

```text
使用 $juejin-article-publisher，按我提供的 Word 修改这篇指定掘金文章的图片位置。保留网页上已经手动修改的正文。
```

## 本地辅助脚本

Python 3.9 或更高版本，均只使用标准库。脚本只做离线准备、映射检查和文件转换，**不负责登录、联网传图或点击发布**。

在技能文件夹内运行，例如：

```bash
python3 scripts/prepare_text.py /absolute/path/article.md --output /absolute/path/new-prepared
python3 scripts/prepare_text.py /absolute/path/article.txt --output /absolute/path/new-txt-prepared
```

TXT 确实使用 Markdown 写法时加 `--txt-as-markdown`；GB18030 文本加 `--encoding gb18030`。文件和图片目录的具体规则见 `references/text-input.md`。

上传图片并从编辑器取得真实托管地址后，按 `references/image-mapping.md` 填写映射，再运行 `scripts/finalize_images.py --help` 所示命令。不能自己编造图床 URL。即使图片数量对得上，也必须核对每张图的位置。

## 运行测试

```bash
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

基础测试仅需标准库；可选安装 `markdown-it-py` 后，还会执行真实 Markdown 渲染的联合检查。未安装时只有该可选检查会跳过，不影响三个辅助脚本运行。

安全提图会拒绝危险 ZIP 路径、重复成员和非空输出目录；预处理与回填也不会覆盖源稿或已有输出。所有测试在临时目录生成虚构材料，不使用真实作者资料。

## 包内资料

- `SKILL.md`：输入分流、发布与验收主流程。
- `references/`：TXT/MD、Word、浏览器、图片回填、验收说明。
- `scripts/`：离线助手及测试。
- `agents/openai.yaml`：技能显示名称和调用提示。

本包按本次实操经验整理，并按 skill-creator 的要求加入了输入边界和独立测试。网站按钮与宿主接口可能更新，实际运行要读取当前页面。平台提示发布成功不代表审核通过，更不代表征文奖励已申请或到账。
