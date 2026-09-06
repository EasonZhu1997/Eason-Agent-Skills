import contextlib
import codecs
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

try:
    import html5lib
except ImportError:
    html5lib = None

import render_richtext as subject


class ObservedHTML(HTMLParser):
    def __init__(self, content):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.data = []
        self.feed(content)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, value):
        self.data.append(value)


@unittest.skipIf(subject.MarkdownIt is None, "Install requirements-render.txt for genuine render tests")
class RenderTests(unittest.TestCase):
    def render(self, value):
        return subject.render_document(value.encode("utf-8"))

    def test_headings_lists_quote_table_and_strike(self):
        source = "# 中文第一章\n\n## 标题二\n\n3. 第一项\n4. 第二项\n\n> 引用\n\n|甲|乙|\n|---|---|\n|一|二|\n\n~~修订~~\n"
        fragment, _, manifest = self.render(source)
        tags = ObservedHTML(fragment).tags
        self.assertIn(("h1", {}), tags)
        self.assertIn(("ol", {"start": "3"}), tags)
        for tag in ("blockquote", "table", "s"):
            self.assertIn((tag, {}), tags)
        self.assertEqual(manifest["headings"], [{"level": 1, "text": "中文第一章"}, {"level": 2, "text": "标题二"}])
        self.assertEqual(manifest["ordered_list_starts"], [3])

    def test_code_content_and_hash_are_exact(self):
        code = '  print("汉字 <script>")\n\treturn "  "\n'
        fragment, _, manifest = self.render("```python\n" + code + "```\n\n`a < b`\n")
        self.assertEqual(manifest["code"][0]["content"], code)
        self.assertEqual(manifest["code"][0]["content_sha256"], hashlib.sha256(code.encode()).hexdigest())
        self.assertIn(code, "".join(ObservedHTML(fragment).data))
        self.assertNotIn(("script", {}), ObservedHTML(fragment).tags)
        self.assertEqual(manifest["code"][1]["content"], "a < b")

    def test_image_order_alt_title_and_signed_query(self):
        url = "https://i-blog.csdnimg.cn/direct/example.png?signature=EXAMPLE%2B%2F&x=1"
        fragment, _, manifest = self.render('![一张 *示意图*](' + url + ' "原说明")\n\n![二图](https://i-blog.csdnimg.cn/second.jpg)\n')
        images = [attrs for tag, attrs in ObservedHTML(fragment).tags if tag == "img"]
        self.assertEqual(images[0]["src"], url)
        self.assertEqual(images[0]["alt"], "一张 示意图")
        self.assertEqual(images[0]["title"], "原说明")
        self.assertEqual([x["order"] for x in manifest["images"]], [1, 2])
        self.assertEqual(manifest["images"][0]["url"], url)

    def test_safe_reference_links_and_anchors_remain(self):
        fragment, _, manifest = self.render("[官方][ref] [邮件](mailto:person@example.com) [节](#section)\n\n[ref]: http://example.com/path?q=1\n")
        self.assertEqual(manifest["links"], ["http://example.com/path?q=1", "mailto:person@example.com", "#section"])
        self.assertEqual(len([x for x in ObservedHTML(fragment).tags if x[0] == "a"]), 3)

    def test_unused_original_image_reference_does_not_block(self):
        fragment, _, manifest = self.render('![蓝图](https://img-blog.csdnimg.cn/blue.png "蓝图标题")\n\n[blue]: <images/蓝 点.png> "蓝图标题"\n')
        self.assertEqual(manifest["baseline"]["image_count"], 1)
        self.assertEqual(manifest["links"], [])
        self.assertNotIn("images/", fragment)

    def test_used_unsafe_reference_is_still_blocked_before_render(self):
        for target in ("relative.md", "file:///etc/passwd", "javascript:example", "data:text/html,example"):
            with self.subTest(target=target), self.assertRaises(subject.ValidationError):
                self.render("[实际使用][ref]\n\n[ref]: " + target + "\n")
        with self.assertRaises(subject.ValidationError):
            self.render("![实际使用][ref]\n\n[ref]: images/a.png\n")

    def test_nested_image_alt_is_not_a_second_rendered_image(self):
        fragment, _, manifest = self.render("![外层 ![内层](https://i-blog.csdnimg.cn/inner.png)](https://i-blog.csdnimg.cn/outer.png)")
        rendered = [a for t, a in ObservedHTML(fragment).tags if t == "img"]
        self.assertEqual(len(rendered), 1)
        self.assertEqual(len(manifest["images"]), 1)
        self.assertEqual(rendered[0]["alt"], "外层 内层")

    def test_html_disabled_not_executed(self):
        fragment, _, manifest = self.render('<script>alert("x")</script>\n\n<img src="https://example.com/a" onerror="alert(1)">\n')
        self.assertFalse(any(tag in ("script", "img") for tag, _ in ObservedHTML(fragment).tags))
        self.assertIn("&lt;script&gt;", fragment)
        self.assertEqual(manifest["images"], [])

    def test_hidden_html_comments_fail_without_leaking_notes(self):
        for text in ("<!-- 内部备注 -->\n正文", "正文 <!-- 内部备注 --> 后文", "> <!-- 内部备注 -->", "<!-- 未闭合内部备注"):
            with self.subTest(text=text), self.assertRaises(subject.ValidationError) as caught:
                self.render(text)
            self.assertNotIn("内部备注", str(caught.exception))

    def test_html_comment_examples_in_code_are_preserved(self):
        source = "`<!-- 字面例子 -->`\n\n```html\n<!-- 代码注释 -->\n```\n\n    <!-- 缩进代码 -->\n"
        fragment, _, manifest = self.render(source)
        self.assertEqual(manifest["baseline"]["code_count"], 3)
        visible = "".join(ObservedHTML(fragment).data)
        for text in ("<!-- 字面例子 -->", "<!-- 代码注释 -->", "<!-- 缩进代码 -->"):
            self.assertIn(text, visible)

    def test_active_and_file_link_schemes_block(self):
        for url in ("javascript:alert%281%29", "JaVaScRiPt:alert%281%29", "data:text/html,example", "file:///etc/passwd", "vbscript:example", "//example.com/a", "relative.md"):
            with self.subTest(url=url), self.assertRaises(subject.ValidationError):
                self.render("[link](" + url + ")")

    def test_active_scheme_character_entities_block(self):
        with self.assertRaises(subject.ValidationError):
            self.render("[link](jav&#x61;script:example)")

    def test_images_require_actual_csdn_cdn_host(self):
        for url in ("http://pic1.i-blog.csdnimg.cn/x.png", "https://i-blog.csdnimg.cn.evil.example/x.png", "https://evili-blog.csdnimg.cn/x.png", "https://a..i-blog.csdnimg.cn/x.png", "https://a.i-blog.csdnimg.cn:444/x.png", "https://user@pic1.i-blog.csdnimg.cn/x.png", "https://pic1.i-blog.csdnimg.cn/", "https://pic1.i-blog.csdnimg.cn./x.png"):
            with self.subTest(url=url), self.assertRaises(subject.ValidationError):
                self.render("![图](" + url + ")")

    def test_csdn_image_hosts_are_exact_not_suffixes_or_article_domains(self):
        for host in ("i-blog.csdnimg.cn", "img-blog.csdnimg.cn"):
            fragment, _, manifest = self.render("![图](https://" + host + "/example.png)")
            self.assertEqual(manifest["baseline"]["image_count"], 1)
            self.assertIn(host, fragment)
        for host in ("csdn.net", "blog.csdn.net", "csdnimg.cn", "pic1.i-blog.csdnimg.cn", "sub.img-blog.csdnimg.cn", "zhimg.com", "picx.zhimg.com", "juejin.cn", "p3-juejin.byteimg.com"):
            with self.subTest(host=host), self.assertRaises(subject.ValidationError):
                self.render("![图](https://" + host + "/example.png)")

    def test_exact_verified_host_override_updates_preview_csp(self):
        source = b"![Example](https://verified.example/image.png?signature=EXAMPLE%2B%2F)"
        with self.assertRaises(subject.ValidationError):
            subject.render_document(source)
        fragment, preview, manifest = subject.render_document(source, ["verified.example"])
        self.assertEqual(manifest["additional_allowed_image_hosts"], ["verified.example"])
        tags = ObservedHTML(preview).tags
        csp = [a["content"] for t, a in tags if t == "meta" and a.get("http-equiv") == "Content-Security-Policy"][0]
        self.assertIn(" https://verified.example;", csp)
        self.assertNotIn("*.verified.example", csp)
        self.assertIn("signature=EXAMPLE%2B%2F", fragment)
        with self.assertRaises(subject.ValidationError):
            subject.render_document(b"![Example](https://sub.verified.example/image.png)", ["verified.example"])

    def test_host_override_rejects_wildcards_ports_paths_and_injection(self):
        for host in ("*.example.com", "UPPER.example", "example.com:443", "https://example.com", "example.com/path", "example.com;script-src", "a..example.com", "example.com'", "example.com."):
            with self.subTest(host=host), self.assertRaises(subject.ValidationError):
                subject.render_document(b"Body", [host])

    def test_cli_host_override_reaches_conversion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "article.md"
            source.write_text("![Example](https://verified.example/image.png)", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                result = subject.main(["--article", str(source), "--output", str(root / "out"), "--allow-host", "verified.example"])
            self.assertEqual(result, 0)
            manifest = json.loads((root / "out" / "manifest.json").read_text())
            self.assertEqual(manifest["additional_allowed_image_hosts"], ["verified.example"])

    def test_placeholders_rejected_even_in_code(self):
        for text in ("![图]({{CS_IMAGE_0001}})", "`{{JJ_IMAGE_001}}`", "{{ZH_IMAGE_0001}}", "{{RK_IMAGE_0001}}", "{{CS_IMAGE_broken}}"):
            with self.subTest(text=text), self.assertRaises(subject.ValidationError):
                self.render(text)

    def test_preview_is_scriptless_with_restricted_csp(self):
        fragment, preview, _ = self.render("# 正文\n")
        self.assertIn(fragment, preview)
        tags = ObservedHTML(preview).tags
        self.assertFalse(any(t == "script" for t, _ in tags))
        csp = [a["content"] for t, a in tags if t == "meta" and a.get("http-equiv") == "Content-Security-Policy"][0]
        self.assertIn("default-src 'none'", csp)
        self.assertIn("https://i-blog.csdnimg.cn", csp)
        self.assertIn("https://img-blog.csdnimg.cn", csp)
        self.assertNotIn("*.", csp)

    def test_literal_txt_markdown_escapes_stay_literal(self):
        fragment, _, manifest = self.render("\\# 不是标题\n\n\\!\\[非图片\\]\\(x.png\\)\n\n&lt;tag&gt;\n")
        self.assertEqual(manifest["images"], [])
        self.assertEqual(manifest["headings"], [])
        self.assertIn("![非图片](x.png)", "".join(ObservedHTML(fragment).data))

    def test_invalid_utf8_and_nul_block(self):
        for value in (b"\xff", b"abc\x00def"):
            with self.subTest(value=value), self.assertRaises(subject.ValidationError):
                subject.render_document(value)

    def test_new_outputs_source_unchanged_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, output = root / "article.md", root / "out"
            raw = b"# Title\n"
            source.write_bytes(raw)
            result = subject.convert_file(source, output)
            self.assertEqual(source.read_bytes(), raw)
            self.assertEqual({p.name for p in output.iterdir()}, {"article.fragment.html", "preview.html", "manifest.json"})
            self.assertEqual(json.loads((output / "manifest.json").read_text()), result)
            with self.assertRaises(subject.ValidationError):
                subject.convert_file(source, output)

    def test_symlink_inputs_and_output_ancestors_block(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "article.md"
            source.write_text("正文", encoding="utf-8")
            linked = root / "linked.md"
            linked.symlink_to(source)
            with self.assertRaises(subject.ValidationError):
                subject.convert_file(linked, root / "out")
            (root / "target").mkdir()
            (root / "linked-dir").symlink_to(root / "target", target_is_directory=True)
            with self.assertRaises(subject.ValidationError):
                subject.convert_file(source, root / "linked-dir" / "out")

    def test_stdout_and_errors_do_not_expose_signed_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "article.md"
            secret_marker = "SIGNATURE-EXAMPLE-ONLY"
            source.write_text("![图](https://i-blog.csdnimg.cn/x.png?sign=" + secret_marker + ")", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(subject.main(["--article", str(source), "--output", str(root / "out")]), 0)
            self.assertNotIn(secret_marker, stdout.getvalue() + stderr.getvalue())
            source.write_text("![图](https://bad.example/x.png?sign=" + secret_marker + ")", encoding="utf-8")
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                self.assertEqual(subject.main(["--article", str(source), "--output", str(root / "out2")]), 1)
            self.assertNotIn(secret_marker, stdout.getvalue() + stderr.getvalue())


class LiteralTextTests(unittest.TestCase):
    def parsed_text(self, fragment):
        if html5lib is None:
            self.skipTest("Optional html5lib==1.1 is needed for actual HTML5 pre newline parsing tests")
        document = html5lib.parseFragment(fragment, namespaceHTMLElements=False)
        pre = document.find("pre")
        self.assertIsNotNone(pre)
        return pre, "".join(pre.itertext())

    def test_html5_parser_preserves_all_spaces_tabs_and_terminal_lines(self):
        original = "\n\n    四个空格\n甲  乙\n\t制表符\n\n\n"
        fragment, _, manifest = subject.render_literal_text(original.encode())
        pre, parsed = self.parsed_text(fragment)
        self.assertEqual(parsed, original)
        self.assertEqual(list(pre), [])
        self.assertNotIn("&nbsp;", fragment)
        self.assertEqual(manifest["baseline"]["literal_text_sha256"], hashlib.sha256(parsed.encode()).hexdigest())
        # Whitespace survives without the auxiliary font styling, not because of CSS.
        _, plain_parsed = self.parsed_text(fragment.replace(' style="font-family:inherit"', ""))
        self.assertEqual(plain_parsed, original)

    def test_html5_parser_treats_markdown_html_and_comments_as_literal_txt(self):
        original = '# 标题\n![图片](https://example.com/a.png)\n<script>alert("x")</script>\n<!--原文-->\n{{CS_IMAGE_0001}}\n'
        fragment, _, manifest = subject.render_literal_text(original.encode())
        pre, parsed = self.parsed_text(fragment)
        self.assertEqual(parsed, original)
        self.assertEqual(list(pre), [])
        self.assertEqual(manifest["images"], [])
        self.assertEqual(manifest["code"], [])
        self.assertEqual(manifest["source_format"], "txt")

    def test_encoding_bom_gb18030_and_newline_normalization(self):
        original = "\r\n中文  内容\r结尾\r\n"
        expected = "\n中文  内容\n结尾\n"
        fixtures = [(codecs.BOM_UTF8 + original.encode("utf-8"), None),
                    (original.encode("utf-16"), None),
                    (original.encode("gb18030"), "gb18030")]
        for raw, encoding in fixtures:
            with self.subTest(encoding=encoding):
                _, _, manifest = subject.render_literal_text(raw, encoding)
                self.assertEqual(manifest["literal_text"], expected)
                self.assertEqual(manifest["source_sha256"], hashlib.sha256(raw).hexdigest())

    def test_plain_txt_cli_does_not_require_markdown_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "literal.txt"
            raw = b"\n    literal  text\n\n"
            source.write_bytes(raw)
            with mock.patch.object(subject, "MarkdownIt", None), contextlib.redirect_stdout(io.StringIO()):
                result = subject.main(["--literal-txt", str(source), "--output", str(root / "out")])
            self.assertEqual(result, 0)
            self.assertEqual(source.read_bytes(), raw)
            manifest = json.loads((root / "out" / "manifest.json").read_text())
            self.assertEqual(manifest["literal_text"], raw.decode())
            self.assertNotIn("source_markdown_sha256", manifest)

    def test_plain_txt_invalid_encoding_nul_and_ambiguous_utf32_fail(self):
        for raw, encoding in ((b"\xff", None), (b"a\x00b", None), (b"body", "does-not-exist"), ("body".encode("utf-32"), None)):
            with self.subTest(encoding=encoding), self.assertRaises(subject.ValidationError):
                subject.render_literal_text(raw, encoding)

    def test_plain_txt_and_markdown_cli_sources_are_mutually_exclusive(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as result:
            subject.main(["--literal-txt", "a.txt", "--article", "b.md", "--output", "new-out"])
        self.assertEqual(result.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
