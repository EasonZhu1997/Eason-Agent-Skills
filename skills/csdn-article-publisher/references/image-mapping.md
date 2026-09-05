# Word 原图与网页位置清单

## 提取

在技能目录运行（输出选一个新的任务目录）：

```bash
python3 scripts/docx_inventory.py --source "/path/to/article.docx" --out "/path/to/task-output"
```

结果包括原始媒体文件和 `manifest.json`。只提取文档原图，不重新绘制。脚本没有网络请求，Python 仅使用标准库。

清单关键字段：

```json
{
  "schema_version": 1,
  "source": {"filename": "article.docx", "sha256": "..."},
  "image_occurrences": 2,
  "unique_media": 2,
  "images": [
    {"order": 1, "relative_path": "media/image-0001.png", "paragraph_index": 2, "caption": null},
    {"order": 2, "relative_path": "media/image-0002.png", "paragraph_index": 7, "caption": "图｜工作流程"}
  ],
  "warnings": []
}
```

实际清单还包含文件指纹、可取得的尺寸和相邻正文。统计的是**出现次数**，不是 ZIP 中媒体文件数；同一文件重复出现须分别归位。

脚本沿正文 XML 的段落顺序读取（包括表格中的段落），不是版面渲染器。无图注、浮动图、正文内嵌图、复杂表格或页眉页脚图片需目视核对，不能把 XML 顺序当绝对视觉顺序。图注是候选，最终锚点须核对。

## 托管 URL 清单

每次上传后，在任务目录维护 `hosted-map.json`，键是图片出现编号：

```json
{
  "1": "https://i-blog.csdnimg.cn/direct/observed-image-one.png",
  "2": "https://i-blog.csdnimg.cn/direct/observed-image-two.png"
}
```

示例地址不能拿去上传；实际值必须来自用户目标编辑器已经上传成功的图片。不要用文章 ID、上传开始提示或本地路径代替图片地址。

## 归位脚本

`scripts/repair_html.mjs` 只修改本地 HTML；它不上传图片、不会保存 CSDN，也不控制浏览器。需要 Node.js 18+，无第三方包。

```bash
node scripts/repair_html.mjs \
  --input "/path/to/original-body.html" \
  --manifest "/path/to/task-output/manifest.json" \
  --urls "/path/to/hosted-map.json" \
  --anchors "/path/to/anchors.json" \
  --output "/path/to/repaired-body.html"
```

输入应是任务开始时留存的干净原文备份。输出拒绝覆盖已有文件，另生成 `.audit.json`。脚本保留原 HTML 的文字、链接及无关格式，清除旧图片及已识别的 CKEditor 图片控件，再插入正式 URL。

默认根据“图｜…”类图注定位，允许括号说明不同或可唯一判断的缩短图注。匹配不到、多个候选、顺序不一致或缺 URL 都会报错，不返回可直接发布的半成品。支持任意正数图片，而非固定篇幅或图片总数。

默认接受常见 CSDN 图片域名。若实际平台使用新域名，在确认是本次上传得到的正式地址后，可传 `--allow-host hostname`；不能随意把任意外链加入白名单。

## 无图注与例外位置

`anchors.json` 可以覆盖指定图片的定位，未覆盖的图片继续依据图注匹配。例如封面在唯一副标题后：

```json
{
  "1": {"text": "从这里开始阅读", "position": "after"}
}
```

- `text` 必须是核对过的完整段落文字，`position` 为 `before` 或 `after`。
- 重复段落可加 `paragraph_index`，指清理旧图片后、包括嵌套段落的零起始段落序号；仅在确认实际位置后使用。
- 多张图需要共用同一锚点时，后续图片可加 `allow_shared_anchor: true`；仍按清单顺序排列。不能用它掩盖未定位问题。
- Word 原图位于一句话中间等无法用段落前后表达的情形，应通过编辑器精确处理，不强行使用脚本。

输出审计列出每张图的锚点、插入方向和 URL。写回网站前要检查这份表，并比较原文文字/链接是否保持。脚本审计通过不等于网站已经接受修改，也不等于图片已经公开可见。
