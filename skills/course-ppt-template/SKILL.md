---
name: course-ppt-template
description: 按 Lesson01、Lesson02 教学版的蓝紫课件规范制作可编辑标准 PPTX。适用于 DSH Flash 根据新课程讲稿生成课件或空白教学模板，使用原页克隆和固定文本槽，避免字体、配色与位置漂移。
---

# 标准课程 PPT 模板

把课程内容写入固定教学版式。模型负责教学组织与短文案，`scripts/pptx_engine.py` 负责 OOXML 页面克隆、文字替换与结构验证。交付普通可编辑 `.pptx`，不把整页截图当课件。

## 开始

1. 读取用户讲稿，保留指定课程名、对象、时长、总页数及内容边界。缺少非关键资料可用明确的教学假设，不编造产品参数、实测结果或来源。
2. 读取本技能的 `references/profile.json`。其中每个 layout 的 `slots` 是唯一允许填写的字段；`max_chars` 包括标点和换行，`max_lines` 是显式行数上限，`max_chars_per_line` 限制每一行的字符数。有 `auto` 的槽由脚本填写，内容 JSON 中不要传这些字段。
3. 界面或网络实操课另读 `references/practical-course-checks.md`，逐项核对课表覆盖、状态一致性和可跟随的操作步骤。
4. 使用用户提供的 `--template`；未指定时检查 `~/.dsh/course-ppt-template/template.pptx`。不存在就按下面的“首次导入”操作。不要另画一套类似模板，也不要假装已经安装。

## 课程组织

按实际课程需要选择页面，可重复同一页型；用户指定 N 页就是总计 N 页。七种页型：

- `cover`：课程封面。`title` 显式分为 2–3 行，每行不超过 8 个汉字；讲师字段保持简短。
- `overview`：四个目标/回顾点及右侧三项提示。
- `section`：章节导语和三个学习目标。主标题最多 6 个字符，只用 1 行，避免撞上右侧目标栏。
- `concepts`：三个核心知识点及总结框，无绑定 AI 产品含义的图标。每条正文和总结框正文只用一行，总结小标题最多 4 字；需要多行讲解时另选版式或分页。
- `comparison`：双栏对照及底部三个观察点。左右标签尽量 4–6 字。左右正文最多两行，给底部说明留出空间。
- `exercise`：三道问题或三项练习。时长由课程需求决定，不编造答案。
- `closing`：一句结课总结及四个产出标签。大标题最多两行，每行不超过 12 个字符。

信息较多时优先精简或在允许的总页数内分页。保持原模板字号、颜色、背景、边框、位置和图像比例。不要临时缩字号、重画装饰、换字体，或用未确认数字填充课堂内容。较长英文也要计入槽位预算。

## 内容文件与生成

内容只含下面的字段，UTF-8 JSON，不带 Markdown 围栏：

```json
{
  "title": "手机摄影入门",
  "slides": [
    {
      "layout": "cover",
      "slots": {
        "title": "手机摄影\n入门实践",
        "presenter": "主讲：课程讲师"
      }
    }
  ]
}
```

除 auto 槽外，每页必须提供该 layout 全部 slots，不能有未知字段或空文字。上述示例只演示封面，实际内容按用户的总页数完整填写。

用当前宿主的文件工具保存 `content.json`，再执行（`SKILL_DIR` 表示本技能所在目录，需要替换成真实路径）：

```bash
python3 SKILL_DIR/scripts/pptx_engine.py build --template TEMPLATE.pptx --profile SKILL_DIR/references/profile.json --content content.json --output 课程.pptx
python3 SKILL_DIR/scripts/pptx_engine.py validate --pptx 课程.pptx --template TEMPLATE.pptx --profile SKILL_DIR/references/profile.json --content content.json
```

遇到文字预算错误，改短对应槽位再生成。不得修改校验规则绕过错误。脚本默认不覆盖已存在的文件；确认属于本次生成物时可用 `--force`。

## 首次导入

本仓库不分发用户的品牌课件、视频或原始课程资料。此 profile 对应 `Lesson02_进阶商业化落地实践流程.pptx` 的页 1、2、4、123、8、9、145，必须提供该版本文件。脚本会核对尺寸与文本槽 ID；其他版本需先重新检查并调整 profile，不能直接套槽位。

```bash
python3 SKILL_DIR/scripts/pptx_engine.py bootstrap --source Lesson02_进阶商业化落地实践流程.pptx --profile SKILL_DIR/references/profile.json --output ~/.dsh/course-ppt-template/template.pptx
```

缓存保留七类页面需要的原图、母版、布局与主题，清理其他课程页、讲者备注、隐藏旧稿描述及外部链接。封面去掉与讲师条重叠的旧日期槽。缓存仅供本机生成，不随技能公开上传。参考差异见 `references/design-notes.md`。

## DSH 调用

将完整技能目录放入 `~/.dsh/skills/course-ppt-template/` 或项目 `.dsh/skills/course-ppt-template/`，在 DSH 中要求使用此技能。也可运行 `scripts/run_dsh.py --help`，以现有 DSH 本机账号执行一次非交互任务，显式选择模型，保留本次输出和调用记录。

本机验证模型为 `deepseek-flash`。`flash1017` 与 `deepseek-flash1017` 曾被当前账号 API 返回 400；不宣称它们等同于 `deepseek-flash`，不静默切换失败的模型。用户指定其他入口时沿用其已配置 provider，不复制密钥到技能。

## 验收与交付

- 结构验证通过后，用 `scripts/render_review.py 课程.pptx --out 预览目录` 导出 PDF/PNG。它调用本机 LibreOffice 和 Poppler，缺少工具时如实说明；也可用 WPS/PowerPoint 打开检查。
- 查看全部页面，核对中文显示、标题换行、边界、页码、课程内容、版式一致性和可编辑文字。若中文缺字，先排查渲染环境的字体，不把缺字截图当成功。
- 检查每个页型至少一页。结构检查不能替代画面检查，未渲染只能报告“结构已验，画面待验”。
- 返回 PPTX 的真实路径。公开仓库只上传技能说明、脚本、profile 与通用示例；不自动上传原课件、缓存、用户讲稿、运行日志或凭据。
