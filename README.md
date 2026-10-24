# Eason Agent Skills

面向内容创作、图文发布、技术表达与 Rokid AI 应用开发的个人 AI 技能库。作者：Eason（[EasonZhu1997](https://github.com/EasonZhu1997)）。

每个技能都是独立目录，包含 `SKILL.md`，以及该流程需要的参考说明、辅助脚本和测试。它们帮助支持技能的 AI 助手完成工作，**不是双击即可自动登录、上传或发布的软件**。

## 技能目录

| 技能 | 用途 | 使用说明 |
| --- | --- | --- |
| CSDN 图文发布 | Word、TXT、Markdown 发布与图片修复，按需通过官方助手同步掘金、知乎 | [说明](skills/csdn-article-publisher/README.md) |
| Rokid 论坛图文发布 | Word、TXT、Markdown 图文发帖，论坛图片结构与标题层级恢复 | [说明](skills/rokid-article-publisher/README.md) |
| 掘金图文发布 | TXT、Markdown、Word 中间稿，原生传图与 Markdown 编辑器校对 | [说明](skills/juejin-article-publisher/README.md) |
| 知乎图文发布 | Word 原生导入、TXT 原文保真、Markdown 富文本转换与发布校对 | [说明](skills/zhihu-article-publisher/README.md) |
| 蓝墨纸绘 | 暖白纸张、黑色线稿、蓝墨标注与少量黄色强调的关系图、流程图和架构图 | [技能](skills/blue-ink-paper-diagram/SKILL.md) |
| 粉笔板书 | 黑板手绘方法论信息图，一页一个问题，支持流程、对比、模块矩阵与底部总结 | [说明](skills/chalkboard-explainer/README.md) |
| 白板手绘 | 近白板面、深色马克笔字和浅色高亮，支持工作坊、流程、对比与方法论图解，附示例图 | [说明](skills/whiteboard-explainer/README.md) |
| 架构图设计能力 | 分层系统总览、跨层业务流程与可编辑 SVG 图表 | [说明](skills/architecture-diagram-design/README.md) |
| Rokid × EverMind（独立仓库） | AIUI JavaScript SDK、Rokid SDK × EverMe Skill 与中英日图文指南 | [前往专属仓库](https://github.com/EasonZhu1997/Rokid-EverMind-Skills) |

各技能支持的格式与限制以其说明为准，不把某一平台的按钮、图床域名或编辑器规则套用于其他平台。

Rokid 记忆接入方案已迁至独立的 [Rokid-EverMind-Skills](https://github.com/EasonZhu1997/Rokid-EverMind-Skills)，用于对外分享。AIUI 路线以可复用 **JavaScript SDK** 为主，Rokid SDK 路线提供眼镜端应用的 EverMe 接入 Skill；新版三语说明附 18 张蓝墨手绘图和 SDK 验证记录。本仓库保留历史发布与兼容代码，最新说明和下载请使用专属仓库。

四个发布技能均支持 `.txt`、`.md` / `.markdown` 和 `.docx` 来源。纯 TXT 默认保留字面文字，不擅自把首行改为标题；配图 Markdown 按出现位置清点并原生上传。复杂嵌套图片、公式或外链等仍需按各平台说明规范与核对，不等于支持所有编辑器扩展。

## 快速开始

1. 下载整个仓库，或克隆：

   ```bash
   git clone https://github.com/EasonZhu1997/Eason-Agent-Skills.git
   ```

2. 找到 `skills/` 内需要的技能。将整个技能目录交给你的 AI 助手，要求它先读取 `SKILL.md`，不要只复制单个主文件。
3. 如需本地自动发现，按当前宿主要求放入技能目录。Codex 当前官方文档列出的个人目录为 `~/.agents/skills/`、项目目录为 `.agents/skills/`；已有同名技能时先比较和备份，不直接覆盖。参见 [官方技能说明](https://learn.chatgpt.com/docs/build-skills#where-to-save-skills)。
4. 在支持 `$技能名` 的宿主里调用；其他宿主使用其技能选择界面或直接提供目录。未配置浏览器交互或图片生成能力时，先完成本地准备并说明缺项。

例如：

```text
使用 $zhihu-article-publisher，将我的 article.md 和同目录 images 文件夹里的图片整理到知乎草稿。保留标题和代码，先不要发布。
```

```text
使用 $juejin-article-publisher，按我指定的 Word 修复这篇掘金文章的图片位置，保留网页中我手动改过的正文。
```

```text
使用 $csdn-article-publisher，把 article.md 和同目录 images 中的图片整理到 CSDN 草稿，按当前编辑器选择 Markdown 或富文本录入。
```

```text
使用 $csdn-article-publisher，将已确认的 CSDN 文章同步到掘金和知乎，优先用官方同步助手；逐站核对图片与格式，先只保存草稿。
```

```text
使用 $rokid-article-publisher，把 article.txt 整理到 Rokid 论坛草稿，保留连续空格、缩进和换行，先不要发布。
```

```text
使用 $blue-ink-paper-diagram，把我提供的流程画成蓝墨纸绘风格，准确区分开发、实测与发布。
```

```text
使用 $chalkboard-explainer，把这份讲稿画成一张粉笔板书，先讲问题与关系，再突出核心结论；文字用自然中文。
```

```text
使用 $whiteboard-explainer，把这份工作流程画成白板马克笔风格，一页讲清步骤、检查点与返工方向。
```

```text
使用 $architecture-diagram-design，根据项目资料先画分层架构总览，再叠加一条跨层业务流程。保留可编辑 SVG，所有未确认的部署关系标为待核实。
```

## 环境与边界

- 辅助脚本通常使用 Python 3.9+；CSDN 的 HTML 助手需要 Node.js，具体依赖见各技能说明。
- CSDN、Rokid 和知乎的 Markdown 富文本转换需要 `markdown-it-py`；其纯 TXT 路线只使用标准库。CSDN 的 Markdown 编辑器路线不必先渲染 HTML。仅在合适的虚拟环境安装所需依赖，不将环境、依赖源码或登录态打进技能目录。
- 发布需要用户自己的账号、当前可用的浏览器交互工具，以及本次明确的上传 / 发布授权。技能不包含 Cookie、密钥、账号、真实文章或图片托管签名。
- 蓝墨纸绘、粉笔板书与白板手绘需要宿主提供图片生成能力才能成图，也可按要求只整理绘图提示词。本仓库不附带来源授权未明确的参考图片，文字风格规范可独立使用；用户也可以提供有权使用的参考图。白板手绘附有通用示例图及其生成提示词。
- 架构图设计能力附带通用假设示例、可编辑 SVG 与 PNG 预览，不复制用户参考图中的品牌 Logo、网址或未经核实的产品参数；修改 SVG 后应重新渲染并检查文字、箭头和边界。
- 本地脚本成功不等于平台保存或发布成功。图片顺序、图注、代码、标题、链接和正式页状态仍需逐项验证。
- CSDN 技能支持用户明确选择后的官方多平台同步，通常先进入掘金/知乎草稿并逐站验收；不会因发布 CSDN 自动向其他站点公开发布。官方助手需要实际可用的扩展与登录条件，详见其说明。本仓库不自动报名、填写奖励问卷或申请奖金。

## 测试

测试使用合成资料或本地静态检查，不对真实账号上传或发布。参考 [验证记录](docs/validation.md) 和各技能的测试命令。网站入口可能变化，首次使用时仍需重新观察页面；本仓库不承诺未来页面的导入、粘贴或审核一定成功。

## 贡献与维护

欢迎通过 Issue 描述可复现的问题，或提交小范围 PR。请注明技能名称、输入类型、宿主与复现步骤，并使用脱敏的最小样例。不要提交密码、Cookie、真实联系方式、私有稿件、签名图片地址或用户截图。

新增或修改技能时同步检查其参考文件、输入边界与测试，保留用户意图和外部操作的授权要求。

## 许可

本仓库原创技能说明与辅助脚本采用 [MIT License](LICENSE)。依赖、外部文档与用户提供的素材保留各自的许可；参见 [来源与第三方说明](THIRD_PARTY_NOTICES.md)。本项目不是各平台的官方产品，也不授予任何平台账号或素材的使用权。
