# 发布前验证记录

验证日期：2026-09-06。检查对象为本仓库发布副本，不修改原始技能或桌面分享包。

## 本地测试结果

| 技能 | 执行结果 | 范围 |
| --- | --- | --- |
| CSDN 图文发布 | 29 项通过 | 14 项 Python DOCX 清单测试，15 项 Node HTML 修复测试 |
| Rokid 论坛图文发布 | 28 项通过 | 14 项 DOCX 清单测试，14 项图片映射测试 |
| 掘金图文发布 | 86 项通过 | TXT/MD 准备、Word 提图、图片回填及解析联合测试 |
| 知乎图文发布 | 118 项通过 | Word 提图、TXT 原文保真、Markdown、图片回填与富文本渲染 |
| 蓝墨纸绘 | 静态检查通过 | 主技能、风格规范、提示模板及显示元数据；未进行新一轮出图 |

合计 261 项本地测试执行通过。五个技能均通过技能结构验证；重复使用的通用组件也在各自目录独立执行，以上不是去重后的算法案例数量。

测试使用合成文章与小图片，不登录账号、不上传文章、不运行文章中的示例代码。完整测试环境含 `markdown-it-py` 和可选的 `html5lib`；缺少这些依赖时部分测试会跳过，不能把跳过记录当成完整通过。

## 自行复验

在仓库根目录，使用 Python 3.9+ 和 Node.js 18+：

```bash
python3 -B -m unittest discover -s skills/csdn-article-publisher/scripts -p 'test_*.py' -v
node --test skills/csdn-article-publisher/scripts/test_repair_html.mjs
python3 -B -m unittest discover -s skills/rokid-article-publisher/scripts -p 'test_*.py' -v
python3 -B -m unittest discover -s skills/juejin-article-publisher/scripts -p 'test_*.py' -v
python3 -B -m unittest discover -s skills/zhihu-article-publisher/scripts -p 'test_*.py' -v
```

要执行 Markdown 和 HTML5 联合检查，在自己的合适虚拟环境中安装知乎目录的 `requirements-render.txt`，并按其参考说明选择可选测试依赖。不要把虚拟环境、依赖源码或生成稿提交到仓库。

## 分发检查

- 四个发布技能只包含通用说明、脚本与合成测试，不附实际文章、截图、账号、Cookie 或图片托管映射。
- 发布前扫描了凭据模式、私人路径和历史文章标识；未发现真实敏感信息。文档中的通用临时目录示例、合成测试中的假签名不是实际凭据。
- 蓝墨纸绘的历史参考图片不在仓库中；公开版无私有图片依赖，使用文字规范或用户授权的参考图。
- 根目录与五个技能目录都附有 MIT 许可证。外部工具、文档及未来用户素材不被重新授权为本仓库原创内容。
- 原有源包保留；本仓库仅做必要的公开分发、安装说明与参考资源可移植性调整。

## 未验证范围

本次没有重新操作四个平台的正式发帖流程，也没有创建公开测试文章、进行奖金申报或重新生成蓝墨纸绘图片。页面导入、富文本清理、懒加载、账号权限及审核结果需在实际使用时按技能说明核对。本地测试通过不能代替正式页验收，也不能保证扫描穷尽所有敏感信息模式。
