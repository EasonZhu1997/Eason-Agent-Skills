# 白板示例生成记录

- 示例：先说清楚，再开始做。
- 生成日期：2026-09-10。
- 工具：宿主内置图像生成工具；未使用外部参考图片。
- 图片：[whiteboard-workflow-example.png](../assets/whiteboard-workflow-example.png)。
- 实际尺寸：1659 × 948 像素，PNG，宽高比 7:4。技能的默认设计比例为 16:9；本张预览保留工具实际输出尺寸，不冒充严格 16:9。
- SHA-256：`7963cc4ded770e49853d79f08a176e14c92fa29cc9b594aa93c617eb3f35d98b`。

已查看实际输出，核对中文与模块文字、深色字和浅黄衬底、主线以及反馈回路：对照检查后的“符合”指向整理交付，“不符合”返回小步实现。绿色是条件标签，不是已完成标记。左侧检查清单为通用图标，不代表真实验收记录。

这是通用工作法示例，不是具体产品的官方流程或实际完成证明。图像是位图，没有可编辑 SVG/PPT 源文件。生成工具可能产生构图和尺寸差异，复用时仍需检查实际结果。

## 本次实际提示词

下列文本保留本次生成请求，包括其中宽幅尺寸的示例。它是生成记录，不覆盖技能的默认规则；新任务要求严格 16:9 时应给出一致的尺寸提示并核对成图。

```text
Use case: infographic-diagram.
Create one original Chinese whiteboard marker hand-drawn methodology infographic as a sample for a reusable whiteboard-explainer skill. Wide 16:9 landscape composition, ideally 1792 x 1024 or a similar wide format. Flat straight-on almost-white smooth dry-erase board fills the image. Black and deep navy marker handwriting, smooth continuous rounded and chisel-tip strokes, slight ink overlap and pressure variation. No paper grain, no chalk powder, no dark background, no heavy reflections, no surrounding classroom, no logo, no watermark. Crisp readable Chinese, authentic marker sketch feel rather than typeset corporate cards. Comfortable margins.

The image explains a generic proposed workflow, not a report of completed work. No completed checkmarks on stages. One main question only. Main title at top in large bold dark-blue hand lettering exactly: "先说清楚，再开始做". Broad pale-yellow highlighter swash behind a few title words, always dark text over yellow. Subtitle exactly: "白板手绘方法论 · 通用示例".

Middle body: left one-third is a hand-drawn blue outlined group titled "先对齐". Three stacked concise numbered items with dark text, small simple marker icons, and clear hierarchy:
"目标" followed by "要得到什么结果？"
"边界" followed by "这次做什么、不做什么？"
"验收" followed by "怎样判断已经做好？"
Use small generic target, boundary brackets, and checklist-outline doodles, not real brand icons.

The right two-thirds group title: "再推进". It is a process, left to right, three medium-large hand-drawn boxes, all with dark lettering and navy borders:
"1 小步实现" with second line "完成一个可检查的改动"
"2 对照检查" with second line "按约定条件检查"
"3 整理交付" with second line "说明结果与待办"
A blue arrow goes box 1 -> box 2.
An arrow from box 2 -> box 3 has a dark green label "符合"; this is a conditional branch label, not a completed status.
A separate red return arrow BELOW the flow starts at the bottom of box 2, loops underneath to the bottom of box 1, arrowhead at box 1. Exact short red text "不符合：回到修改". It must not connect box 3 or point back from delivery.
Have sufficient vertical space for this feedback loop, no overlapping lines or words.
Very small navy pen and document-outline doodles can decorate the group; no person is needed.

Bottom full-width conclusion strip, blue outlined with subtle pale-yellow highlight behind the label, dark-blue text exactly:
Label "核心原则"
Sentence "先约定结果，再分步推进，每一步都能检查。"
Keep one conclusion sentence. Use only the exact listed text, no extra claims, no numeric performance results, no page number. Main title > group headings > node headings > explanatory notes. Readable when displayed in a repository README. Whiteboard marker aesthetic consistent for text, borders, arrows and all doodles.
```
