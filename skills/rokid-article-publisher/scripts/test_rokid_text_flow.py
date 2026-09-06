"""Rokid-specific output tests; all fixtures and hosts are synthetic."""

import contextlib
import hashlib
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import finalize_images as finalizer
import prepare_text as preparer
import render_richtext as renderer


class FragmentTree(HTMLParser):
    def __init__(self, fragment):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.images = []
        self.starts = []
        self.feed(fragment)

    def handle_starttag(self, tag, attrs):
        self.starts.append(tag)
        if tag == "img":
            self.images.append((list(self.stack), dict(attrs)))
        if tag not in {"img", "br", "hr", "meta", "link", "input"}:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()


@unittest.skipIf(renderer.MarkdownIt is None, "Install requirements-render.txt for actual Markdown rendering")
class RokidTextFlowTests(unittest.TestCase):
    def render(self, source):
        return renderer.render_document(source.encode(), ["native-upload.example"])

    def test_standalone_image_is_semantically_top_level_not_css_only(self):
        fragment, _, manifest = self.render('# 章\n\n前文\n\n![图](https://native-upload.example/one.png "说明")\n\n图｜图注\n')
        tree = FragmentTree(fragment)
        self.assertEqual(tree.starts, ["h1", "p", "img", "p"])
        self.assertEqual(tree.images[0][0], [])
        self.assertEqual(tree.images[0][1]["width"], "100%")
        self.assertEqual(tree.images[0][1]["title"], "说明")
        self.assertEqual(manifest["baseline"]["image_count"], 1)

    def test_images_caption_adjacency_and_original_order(self):
        source = "![甲](https://native-upload.example/a.png)\n\n图｜甲\n\n## 中间章节\n\n![乙](https://native-upload.example/b.png)\n\n图｜乙\n"
        fragment, _, manifest = self.render(source)
        self.assertEqual([a["src"] for _, a in FragmentTree(fragment).images], [i["url"] for i in manifest["images"]])
        self.assertTrue(fragment.index("a.png") < fragment.index("图｜甲") < fragment.index("中间章节") < fragment.index("b.png") < fragment.index("图｜乙"))
        self.assertTrue(all(not parents for parents, _ in FragmentTree(fragment).images))

    def test_mixed_text_image_paragraph_refuses_instead_of_splitting(self):
        for source in ("前文 ![图](https://native-upload.example/a.png) 后文", "前文\n![图](https://native-upload.example/a.png)", "![图](https://native-upload.example/a.png)\n图注"):
            with self.subTest(source=source), self.assertRaisesRegex(renderer.ValidationError, "standalone image"):
                self.render(source)

    def test_multiple_images_in_one_paragraph_refuse(self):
        for separator in (" ", "\n", "  \n"):
            with self.subTest(separator=separator), self.assertRaises(renderer.ValidationError):
                self.render("![甲](https://native-upload.example/a.png)" + separator + "![乙](https://native-upload.example/b.png)")

    def test_linked_image_refuses_without_discarding_link(self):
        with self.assertRaises(renderer.ValidationError):
            self.render("[![图](https://native-upload.example/a.png)](https://example.com/reference)")

    def test_list_image_refuses_container_rewrite(self):
        for prefix in ("- ", "1. ", "- 正文\n\n  "):
            with self.subTest(prefix=prefix), self.assertRaises(renderer.ValidationError):
                self.render(prefix + "![图](https://native-upload.example/a.png)")

    def test_quote_image_refuses_container_rewrite(self):
        with self.assertRaises(renderer.ValidationError):
            self.render("> ![图](https://native-upload.example/a.png)")

    def test_table_image_refuses_container_rewrite(self):
        with self.assertRaises(renderer.ValidationError):
            self.render("|项目|图|\n|---|---|\n|甲|![图](https://native-upload.example/a.png)|\n")

    def test_emphasis_wrapped_image_refuses(self):
        with self.assertRaises(renderer.ValidationError):
            self.render("**![图](https://native-upload.example/a.png)**")

    def test_zero_images_needs_no_host_or_default_network_permission(self):
        fragment, preview, manifest = renderer.render_document(b"# Title\n\nBody\n")
        self.assertEqual(manifest["images"], [])
        self.assertIn("img-src 'none';", preview)
        self.assertNotIn("https://", preview)
        self.assertIn("<h1>Title</h1>", fragment)

    def test_no_implicit_platform_or_broad_storage_hosts(self):
        for host in ("forum.rokid.com", "rokid.com", "picx.zhimg.com", "img-blog.csdnimg.cn", "aliyuncs.com", "bucket.oss-cn.example.com"):
            url = "https://" + host + "/example-only.png"
            with self.subTest(host=host):
                with self.assertRaises(finalizer.ValidationError):
                    finalizer.validate_url(url)
                with self.assertRaises(renderer.ValidationError):
                    renderer.render_document(("![图](" + url + ")").encode())

    def test_exact_host_does_not_authorize_child_or_sibling(self):
        for host in ("child.native-upload.example", "native-upload.example.evil.example", "other-upload.example"):
            with self.subTest(host=host):
                with self.assertRaises(finalizer.ValidationError):
                    finalizer.validate_url("https://" + host + "/image.png", ["native-upload.example"])
                with self.assertRaises(renderer.ValidationError):
                    self.render("![图](https://" + host + "/image.png)")

    def test_legacy_placeholders_not_accepted_as_ready_markdown(self):
        for token in ("{{RK_IMAGE_0001}}", "{{ZH_IMAGE_0001}}", "{{JJ_IMAGE_0001}}", "{{CS_IMAGE_0001}}", "{{CSDN_IMAGE_0001}}", "{{IMAGE_1}}"):
            with self.subTest(token=token), self.assertRaises(renderer.ValidationError):
                renderer.render_document(("`" + token + "`").encode())

    def test_prepare_finalize_render_full_local_roundtrip(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source = root / "article.md"
            (root / "diagram.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"synthetic-image-for-inventory")
            source.write_text('# 原标题\n\n![图][ref]\n\n图｜原图注\n\n```python\n  print("a  b")\n```\n\n[ref]: diagram.png "原说明"\n', encoding="utf-8")
            original = source.read_bytes()
            manifest = preparer.prepare(source, root / "prepared")
            self.assertTrue(manifest["ready_for_upload"])
            entry = manifest["images"][0]
            self.assertEqual(entry["placeholder"], "{{RK_IMAGE_0001}}")
            url = "https://native-upload.example/example-only.png?token=EXAMPLE%2b%2F&x=1&x=2"
            mapping = {entry["placeholder"]: {"url": url, "source_sha256": entry["sha256"]}}
            prepared = (root / "prepared/article.md").read_bytes()
            with self.assertRaises(finalizer.ValidationError):
                finalizer.finalize_bytes(prepared, manifest, mapping, root / "prepared")
            ready = finalizer.finalize_bytes(prepared, manifest, mapping, root / "prepared", ["native-upload.example"])
            with self.assertRaises(renderer.ValidationError):
                renderer.render_document(ready)
            fragment, _, rendered = renderer.render_document(ready, ["native-upload.example"])
            self.assertEqual(FragmentTree(fragment).images[0], ([], {"src": url, "alt": "图", "title": "原说明", "width": "100%", "style": "height:auto;max-width:100%;"}))
            self.assertEqual(rendered["code"][0]["content"], '  print("a  b")\n')
            self.assertEqual(rendered["source_sha256"], hashlib.sha256(ready).hexdigest())
            self.assertEqual(source.read_bytes(), original)

    def test_incompatible_image_does_not_create_partial_outputs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            source, out = root / "article.md", root / "out"
            source.write_text("前 ![图](https://native-upload.example/a.png) 后", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = renderer.main(["--article", str(source), "--output", str(out), "--allow-host", "native-upload.example"])
            self.assertEqual(code, 1)
            self.assertFalse(out.exists())


class RokidLiteralTextTests(unittest.TestCase):
    def test_literal_txt_runs_without_markdown_dependency_or_hosts(self):
        original = "\n    # 原文  空格\n\t![非图片](missing.png)\n\n"
        with mock.patch.object(renderer, "MarkdownIt", None):
            fragment, preview, manifest = renderer.render_literal_text(original.encode())
        self.assertEqual(manifest["literal_text"], original)
        self.assertEqual(manifest["images"], [])
        self.assertIn("img-src 'none';", preview)
        self.assertEqual(FragmentTree(fragment).starts, ["pre"])


if __name__ == "__main__":
    unittest.main()
