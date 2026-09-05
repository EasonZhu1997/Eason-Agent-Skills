# 知乎图文发布技能 · 分享包

与同系列图文发布包一样，包含技能说明、可运行助手、参考资料与合成测试。用途是帮助 AI 助手把文章整理到知乎，或修复指定文章的图文与排版；不是双击后自动登录、发布的软件。

## 支持的文件

| 来源 | 路线 |
| --- | --- |
| TXT | 原文生成预格式文本，保留换行、缩进和连续空格；不解析 Markdown 标点 |
| MD / Markdown | 清点配图并回填托管地址，转换成知乎可用的富文本内容 |
| Word DOCX | 优先使用当前编辑器确实提供的原生文档导入；先提图清点，再校对导入结果 |

支持纯文字稿。缺图、路径越界或无法可靠处理的结构会明确阻断；不把图片丢了当成功。Word 原生导入仍可能需要恢复标题、代码与链接；没有入口时，可用确认过的 Markdown 导出稿或已安装的可信转换器。

## 分享与使用

把整个 `zhihu-article-publisher` 文件夹或配套 ZIP 发给对方，**不要只复制 SKILL.md**。所有本包引用的脚本和说明均在文件夹内，不依赖作者的桌面、真实文章或账号。

使用者需要支持技能的 AI 助手、可用的浏览器交互工具和自己的知乎账号。登录和验证码按宿主要求操作；本包不包含 Cookie、密码或 API key，也不自动安装插件。

可以直接把解压后的目录交给助手：

> 请使用这个目录中的 SKILL.md，把我提供的文章整理到知乎草稿，保留标题、代码和图片位置，先不要发布。

如需自动发现，将文件夹放入当前宿主的技能目录。OpenAI 当前文档列出的 Codex 个人目录为 `~/.agents/skills/`、项目目录为 `.agents/skills/`；旧版本以实际配置为准，避免重复安装。解压到桌面不等于已经安装。参见 [OpenAI 官方技能说明](https://learn.chatgpt.com/docs/build-skills#where-to-save-skills)。

安装后示例：

```text
使用 $zhihu-article-publisher，把 article.txt 整理到知乎草稿，先不发布。
```

```text
使用 $zhihu-article-publisher，把 article.md 和同目录 images 中的图片发布到知乎。不要改标题，检查每张图的位置。
```

```text
使用 $zhihu-article-publisher，按附件 Word 修复这篇指定知乎文章的图片和标题层级，保留网页上我手动改过的正文。
```

## 本地脚本

Python 3.9+。提图、TXT 直转、TXT/MD 预处理和映射回填仅用标准库。Markdown 富文本渲染额外需要 `markdown-it-py`；要求记录在 `requirements-render.txt`，不会随技能调用自动安装。若环境没有依赖，可由使用者在自己的虚拟环境安装，或使用已有可信转换器；不能假称 Markdown 渲染已完成。

在技能目录运行：

```bash
python3 scripts/render_richtext.py --literal-txt /absolute/path/article.txt --output /absolute/path/new-txt-richtext
python3 scripts/prepare_text.py /absolute/path/article.md --output /absolute/path/new-md-prepared
python3 scripts/docx_inventory.py --source /absolute/path/article.docx --out /absolute/path/new-word-inventory
```

TXT 确实采用 Markdown 写法时改用 `prepare_text.py` 并加 `--txt-as-markdown`；GB18030 文本显式加 `--encoding gb18030`。Markdown 清单检查通过后，按 `references/image-mapping.md` 上传、回填，再按 `references/richtext.md` 渲染。纯 TXT 不需要图片清单和回填，其预格式文本用于保留原空白；若希望改为普通段落或重新设计层级，需按用户另行指定的排版要求处理。

脚本不登录、不联网上传、不点击发布，也不执行文章里的代码。已有输出不会被覆盖。富文本区应使用 HTML 格式粘贴或正常复制渲染内容，不把 Markdown 源码直接粘贴当成正确排版。

## 测试与限制

```bash
python3 -B -m unittest discover -s scripts -p 'test_*.py' -v
```

未安装渲染依赖时，相关渲染测试会跳过；可选的 `html5lib` 仅用于 HTML5 文本保真测试，不是运行依赖。具备这些测试依赖后可执行完整转换链路检查。测试仅使用临时生成的虚构文章和小图片，不接触真实账号或发布页面。

本地测试通过不证明某个未来页面的导入、粘贴、图片转存或审核一定成功。运行时仍需观察当前 UI，校对编辑器和正式页；网站不提供某项入口时会说明缺项，不绕过安全限制。

## 包内结构

- `SKILL.md`：按输入类型选择流程、授权范围与交付标准。
- `references/`：文本、Word、图片、富文本、浏览器与验收说明。
- `scripts/`：离线助手与测试。
- `requirements-render.txt`：富文本渲染依赖。
- `agents/openai.yaml`：技能显示名称与调用提示。

按 skill-creator 的要求加入了可复用边界和独立测试。只制作技能包不会自动修改已发布文章、填写问卷或申请奖励。
