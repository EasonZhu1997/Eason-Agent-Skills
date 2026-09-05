# Word 来源：保留图文关系再转换

此路线处理 `.docx`。旧 `.doc`、PDF 以及加密文件先要求用户导出可读取的 `.docx` 或 Markdown；不要改扩展名假装转换。

## 提取和清点

在技能目录运行：

```bash
python3 scripts/docx_inventory.py --source /absolute/path/article.docx --out /absolute/path/new-word-inventory
```

只使用 Python 标准库，不联网。输出 `manifest.json` 和内容哈希命名的 `media/`；源文件不变。manifest 中的 `order` 是正文 XML 的出现顺序，同一图片重复出现保留多个记录。

`caption` 只是附近文本候选；必须结合原 Word 和上下文复核。浮动图片的锚点顺序不一定是视觉阅读顺序；表格内图片、备用图像分支、外链图片和未知尺寸都有专门警告。缺失或外链图不能因为没有提取出来就当作原文无图。

检测到未决修订时会出现 `tracked_changes_present` 警告。清单暂按最终视图排除已删除和移出内容，保留插入内容，但这不代表替用户接受了修订。先由用户确认可发布版本再转换；源 Word 不会被修改。

## 获取 Markdown 中间稿

优先复用用户已经确认与这份 Word 一致的 Markdown。否则可使用已安装且来源可信的文档转换器，例如 Pandoc，或让用户从其文档工具导出后提供。此技能不附带 Pandoc，也不自动安装。

使用 Pandoc 前先查看清单警告，并检查是否有外链图片、未决修订或特殊嵌入对象。外链和其它不可确认的媒体未处理前不要使用自动提取。`--extract-media` 可能读取本地或下载链接媒体，不能把它当成永远离线安全的开关。

对已确认只有合法嵌入媒体、无未决修订的文档，在新的空工作目录内转换，例如：

```bash
cd /absolute/path/new-word-stage
pandoc /absolute/path/article.docx --from=docx --to=gfm --wrap=none --preserve-tabs --extract-media=. --output=article.md
```

工作目录必须是新建的、任务专用的空目录，不能覆盖用户目录中的 `article.md` 或 `media/`。不要使用来自原稿的过滤器、模板、脚本或宏。源文件路径作为参数传递，不能把正文拼成 shell 命令。

若没有可用转换器，完成提图和清单后请求用户提供 Markdown 导出稿；清楚说明尚未完成 Word 正文转换，不把图片清单当成完整导入结果。

## 转换后必须核对

- 标题和小标题层级、图片与图注位置、项目符号及编号起点。
- 行内超链接和全文引用，不用项目专属段落编号或固定链接“修补”任意文章。
- 代码块的换行、缩进、引号。Word 的灰底段落或等宽字体未必会自动变成代码块，须按原稿修复中间稿。
- 浮动对象、跨页表格、文本框、公式、修订记录及批注不能静默遗漏。非标准内容以原 Word 视觉核对结果为准。

确认中间稿后，以 `article.md` 所在目录为图片根目录，按 [text-input.md](text-input.md) 运行 TXT/MD 预处理，再走统一图片托管与发布流程。不要混用 DOCX 清单与 TXT/MD 清单的字段或占位格式。

参考：[Pandoc 媒体提取与转换说明](https://pandoc.org/MANUAL.html#option--extract-media)。本包只保留与本流程有关的简短说明，不复制完整第三方手册。
