# Markdown 图片回填：按原位置，不按上传完成先后

这个步骤只处理本地文件。脚本不联网、不上传、不读取浏览器登录态，也不能证明图片已发布。浏览器操作必须通过当前会话支持的界面工具完成。

## 输入与边界

`prepare_text.py` 输出 `article.md`、`manifest.json` 和 `media/`。每次出现一张图片，就得到一个唯一占位符，例如 `{{CS_IMAGE_0001}}`；即使原图相同，也分别保留位置。清单的 `order` 从 1 连续递增。

这套清单只交给 `finalize_images.py`，不是 Word 的 `docx_inventory.py` 清单。Word 清单配数字字符串键和 URL 字符串值，使用 `repair_html.mjs`；此处使用 `CS_IMAGE` 键和对象值，不能互换。生成的富文本验收 `manifest.json` 也不是此处的准备清单。

只有 `blocking_issues` 为空、每张图都是已准备的 `local` 文件且 SHA-256 未变，才可回填。清单还必须有有效的 `baseline.prepared_markdown_sha256`，并与 `article.md` 的原始字节完全匹配；即使图片占位符没变，改正文、换行或给全文套上代码围栏，也会拒绝回填。要修改内容，请改原稿并重新准备，不要手改基线去绕过校验。

远程图片、缺图、越界图片和未确认内容必须先解决：请用户提供有权使用的本地图，改好原稿中的引用后重新准备。不要直接把第三方外链冒充CSDN托管图片，不要为了通过检查手动清空 blocker。

上传时以清单里的原图、占位符、SHA-256 建立对应关系。在编辑器中逐图或小批上传，确认平台生成的图片与原图一致，再记录平台实际返回并已渲染的图片 URL。异步完成顺序不等于原稿顺序；图片尺寸只能辅助核对，不是唯一识别依据。可重复图片允许共享一条已经核对的 URL。

## hosted-map.json 格式

JSON 顶层键必须恰好覆盖所有占位符，每个值包含 `url` 和可选的 `source_sha256`。推荐填写 SHA-256，来源是清单，不是上传后的压缩文件。对象的键顺序无关紧要，重复键会被拒绝。

以下只是格式说明；示例地址并非真实上传结果，不可用于发布：

```json
{
  "{{CS_IMAGE_0001}}": {
    "url": "https://i-blog.csdnimg.cn/example-only/not-a-real-upload.png?signature=EXAMPLE%2B%2F",
    "source_sha256": "填写清单中该图片的64位小写十六进制SHA-256"
  }
}
```

真实映射文件属于当前文章的工作材料，不应装入技能分享包。不要把签名 URL、登录态、手机号、账号信息写进可复用技能或测试。脚本的正常输出和校验错误均不回显 URL；最终 Markdown 自然包含发布所需的图片地址，分享前按需要检查。

## 离线回填

在技能目录执行，替换成实际工作目录：

```bash
python3 scripts/finalize_images.py \
  --manifest /absolute/work/prepared/manifest.json \
  --article /absolute/work/prepared/article.md \
  --hosted-map /absolute/work/hosted-map.json \
  --output /absolute/work/article.ready.md
```

输出文件必须不存在，脚本不会覆盖原稿。成功输出 `ready_for_editor` 表示本地 Markdown 回填完成，不代表已经转换成CSDN富文本，也不代表发布成功。脚本先完成全部校验，再创建新文件；替换之外的正文、换行和代码字节保持原样。

默认仅接受 HTTPS 的精确主机 `i-blog.csdnimg.cn` 和 `img-blog.csdnimg.cn`，不自动允许其子域、普通 `csdn.net` 网页或其他平台图床。只接受实际上传后核实过的图片地址；不能把任意同域链接当作上传成功。未来平台若使用其他图床，必须在当前上传后的界面中核实其准确主机名，再显式添加：

```bash
python3 scripts/finalize_images.py \
  --manifest /absolute/work/prepared/manifest.json \
  --article /absolute/work/prepared/article.md \
  --hosted-map /absolute/work/hosted-map.json \
  --output /absolute/work/article.ready.md \
  --allow-host verified-upload-host.example
```

`--allow-host` 只接受准确的小写主机名，不接受通配符、协议、路径或端口；不要根据外观相似直接放行。URL 的签名参数会原样保留，不会擅自去签名、改域名或猜测无签名地址。如果地址含不适合直接放入 Markdown 的未转义字符，脚本拒绝，需从编辑器取得正确的可用地址，不手工改写签名。

以下情况会失败且不输出新稿：缺少有效正文基线、准备后正文被改动、漏图或多余映射、重复键、占位符丢失/重复/错序、未解决 blocker、源图被替换、源图越界、非平台域、危险协议、URL 用户信息、非 443 端口，以及不同源图意外映射成同一条 URL。

## 发布后验收

先识别当前编辑器：确实为 Markdown 编辑器时，将最终 Markdown 作为源码录入，检查平台预览；富文本编辑器按 [richtext.md](richtext.md) 使用 `scripts/render_richtext.py --article`，再通过支持的 HTML 剪贴板或原生复制粘贴转入。不要把 Markdown 源码直接贴入富文本正文并宣称标题和代码格式已保留。检查标题、各级章节、列表和代码块；发布后刷新真实页面，对照原稿逐图核对位置与图注，再检查图片是否完成加载、尺寸非零。惰性加载图片要滚到相应段落后检查，不能只核对首屏。

总图数相等不等于顺序正确；也不要把草稿中的上传成功视为公开页面显示正常。记录公开链接和实际状态（如“审核中”）。若检查受锁屏、登录或权限限制，明确说明尚未验证的范围。
