#!/usr/bin/env python3
"""Synthetic local fixtures only. Run with python3 -m unittest discover -s scripts."""
import base64
import codecs
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from prepare_text import PreparationError, prepare

try:
    from markdown_it import MarkdownIt
except ImportError:
    MarkdownIt = None

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")


class PrepareTextTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.source_dir = self.root / "source"
        self.source_dir.mkdir()
        self.output = self.root / "output"

    def tearDown(self):
        self.temp.cleanup()

    def source(self, text, name="article.md", encoding="utf-8"):
        path = self.source_dir / name
        path.write_bytes(text.encode(encoding) if isinstance(text, str) else text)
        return path

    def picture(self, name="image.png"):
        path = self.source_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(PNG)
        return path

    def article(self):
        return (self.output / "article.md").read_text(encoding="utf-8")

    def test_utf8_txt_is_literal_and_source_unchanged(self):
        raw = "# 标题\n<script>alert(1)</script>\n\n![not image](missing.png)\n```sh\nrm example\n```\n    indented\n"
        source = self.source(raw, "article.txt")
        result = prepare(source, self.output)
        self.assertEqual(source.read_text(), raw)
        self.assertEqual(result["images"], [])
        self.assertTrue(result["ready_for_upload"])
        self.assertIn("\\# 标题  \n", self.article())
        self.assertIn("&lt;script&gt;", self.article())
        self.assertIn("\\!\\[not image\\]", self.article())
        self.assertIn("\\`\\`\\`sh", self.article())
        self.assertIn("&#32;&#32;&#32;&#32;indented", self.article())
        self.assertEqual(result["baseline"]["heading_count"], 0)
        self.assertEqual(result["baseline"]["code_block_count"], 0)

    def test_utf8_bom(self):
        source = self.source(codecs.BOM_UTF8 + "标题".encode(), "article.txt")
        result = prepare(source, self.output)
        self.assertEqual(result["input_encoding"], "utf-8-sig")
        self.assertNotIn("\ufeff", self.article())

    def test_utf16_bom(self):
        result = prepare(self.source("中文\r\n换行", "article.txt", "utf-16"), self.output)
        self.assertEqual(result["input_encoding"], "utf-16")
        self.assertIn("中文  \n换行", self.article())

    def test_gb18030_requires_explicit_encoding(self):
        source = self.source("中文测试", "article.txt", "gb18030")
        with self.assertRaises(PreparationError):
            prepare(source, self.output)
        self.assertFalse(self.output.exists())
        result = prepare(source, self.output, "gb18030")
        self.assertEqual(result["input_encoding"], "gb18030")

    def test_no_guess_of_utf16_without_bom(self):
        with self.assertRaises(PreparationError):
            prepare(self.source("abc".encode("utf-16-le"), "article.txt"), self.output)

    def test_utf32_requires_explicit_encoding(self):
        source = self.source("中文", "article.txt", "utf-32")
        with self.assertRaises(PreparationError):
            prepare(source, self.output)
        self.assertTrue(prepare(source, self.output, "utf-32")["ready_for_upload"])

    def test_empty_txt(self):
        result = prepare(self.source("", "article.txt"), self.output)
        self.assertEqual(self.article(), "")
        self.assertTrue(result["ready_for_upload"])

    def test_txt_markdown_opt_in(self):
        self.picture()
        result = prepare(self.source("# Title\n![图](image.png)", "article.txt"), self.output, txt_as_markdown=True)
        self.assertEqual(result["baseline"]["heading_count"], 1)
        self.assertEqual(len(result["images"]), 1)
        self.assertIn("# Title", self.article())

    def test_markdown_extension_and_structure(self):
        source = self.source("# Title `code`\n\n## Child\n\n- one\n1. two\n\n```js\nconst x = '<a>';\n```\n\n[link](https://example.invalid/)\n", "article.markdown")
        result = prepare(source, self.output)
        self.assertEqual(self.article(), source.read_text())
        self.assertEqual(result["baseline"]["heading_count"], 2)
        self.assertEqual(result["baseline"]["code_block_count"], 1)
        self.assertEqual(result["baseline"]["list_item_count"], 2)
        self.assertEqual(result["source"]["format"], "markdown")

    def test_inline_images_and_occurrence_placeholders(self):
        self.picture()
        source = self.source("before ![one](image.png) after\n\n![two](image.png \"title\")")
        result = prepare(source, self.output)
        self.assertEqual(self.article(), "before ![one]({{RK_IMAGE_0001}}) after\n\n![two]({{RK_IMAGE_0002}} \"title\")")
        self.assertEqual([x["order"] for x in result["images"]], [1, 2])
        self.assertEqual([x["alt"] for x in result["images"]], ["one", "two"])
        self.assertEqual(len(list((self.output / "media").iterdir())), 1)
        self.assertEqual(result["images"][0]["sha256"], hashlib.sha256(PNG).hexdigest())
        self.assertEqual((self.output / result["images"][0]["relative_path"]).read_bytes(), PNG)

    def test_reference_full_collapsed_shortcut_case_normalized(self):
        self.picture("图 表.png")
        text = "![first][My REF]\n![my ref][]\n![my ref]\n\n[my ref]: <图 表.png> 'caption'\n"
        result = prepare(self.source(text), self.output)
        self.assertEqual(len(result["images"]), 3)
        self.assertTrue(result["ready_for_upload"])
        self.assertIn("[my ref]: <图 表.png> 'caption'", self.article())
        self.assertIn("![first]({{RK_IMAGE_0001}} 'caption')", self.article())

    def test_reference_first_definition_wins(self):
        self.picture()
        result = prepare(self.source("![a][ref]\n\n[ref]: image.png\n[REF]: missing.png\n"), self.output)
        self.assertTrue(result["ready_for_upload"])

    def test_reference_next_line_title_preserved(self):
        self.picture()
        result = prepare(self.source("![a][ref]\n\n[ref]: image.png\n  \"下一行标题\"\n"), self.output)
        self.assertTrue(result["ready_for_upload"])
        self.assertIn('![a]({{RK_IMAGE_0001}} "下一行标题")', self.article())

    def test_reference_definition_cannot_interrupt_paragraph(self):
        self.picture()
        result = prepare(self.source("前文\n[ref]: image.png\n\n![图][ref]\n"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertEqual(result["images"], [])

    def test_reference_label_entities_not_unescaped(self):
        self.picture()
        result = prepare(self.source("![foo&bar]\n\n[foo&amp;bar]: image.png\n"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertEqual(result["images"], [])

    def test_reference_label_backslashes_not_unescaped(self):
        self.picture()
        result = prepare(self.source("![foo\\*]\n\n[foo*]: image.png\n"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertEqual(result["images"], [])

    def test_spaces_parentheses_escape_and_unicode_destinations(self):
        self.picture("图 片(1).png")
        self.picture("foo(bar).png")
        result = prepare(self.source("![一](<图 片(1).png>)\n![二](foo(bar).png)\n![三](foo\\(bar\\).png)\n![四](图%20片%281%29.png)"), self.output)
        self.assertEqual(len(result["images"]), 4)
        self.assertTrue(result["ready_for_upload"])

    def test_image_in_link_keeps_link(self):
        self.picture()
        prepare(self.source("[![alt](image.png)](https://example.invalid/)"), self.output)
        self.assertEqual(self.article(), "[![alt]({{RK_IMAGE_0001}})](https://example.invalid/)")

    def test_code_blocks_inline_and_escaped_fake_images_ignored(self):
        text = "```md\n![fake](no.png)\n```\n\n~~~\n<img src='no.png'>\n~~~\n\n    ![fake](no.png)\n\n`![fake](no.png)` and `` ` ![fake](no.png) ``\n\\![escaped](no.png)\n"
        result = prepare(self.source(text), self.output)
        self.assertTrue(result["ready_for_upload"])
        self.assertEqual(result["images"], [])
        self.assertEqual(self.article(), text)

    def test_four_backtick_fence_protects_inner_three(self):
        text = "````md\n```\n![fake](no.png)\n```\n````\n"
        result = prepare(self.source(text), self.output)
        self.assertTrue(result["ready_for_upload"])
        self.assertEqual(result["images"], [])

    def test_indented_image_continues_ordinary_paragraph(self):
        self.picture()
        result = prepare(self.source("前文\n    ![图](image.png)\n"), self.output)
        self.assertTrue(result["ready_for_upload"])
        self.assertEqual(len(result["images"]), 1)
        self.assertIn("    ![图]({{RK_IMAGE_0001}})", self.article())

    def test_inline_backticks_do_not_span_blank_paragraphs(self):
        self.picture()
        result = prepare(self.source("未闭合 ` 第一段\n\n![图](image.png)\n\n下一段 ` 结束\n"), self.output)
        self.assertTrue(result["ready_for_upload"])
        self.assertEqual(len(result["images"]), 1)

    def test_html_comment_fake_images_ignored(self):
        text = "<!-- ![fake](missing.png) -->\n\n文字 <!-- <img src='missing.png'> -->\n"
        result = prepare(self.source(text), self.output)
        self.assertTrue(result["ready_for_upload"])
        self.assertEqual(result["images"], [])
        self.assertEqual(self.article(), text)

    def test_unclosed_html_comment_blocked(self):
        result = prepare(self.source("<!-- ![fake](missing.png)"), self.output)
        self.assertFalse(result["ready_for_upload"])

    def test_comment_backtick_does_not_hide_following_image(self):
        self.picture()
        result = prepare(self.source("前文 <!-- ` --> ![图](image.png) ` 后文"), self.output)
        self.assertTrue(result["ready_for_upload"])
        self.assertEqual(len(result["images"]), 1)

    def test_comment_delimiters_inside_inline_code_fail_closed(self):
        self.picture()
        result = prepare(self.source("`<!--` ![图](image.png) `-->`"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertTrue(any("comment_code_interaction" in issue for issue in result["blocking_issues"]))

    def test_remote_and_protocol_relative_never_downloaded(self):
        result = prepare(self.source("![a](https://example.invalid/a.png)\n![b](//example.invalid/b.png)"), self.output)
        self.assertEqual([x["kind"] for x in result["images"]], ["remote", "remote"])
        self.assertFalse(result["ready_for_upload"])
        self.assertFalse((self.output / "media").exists())
        self.assertNotIn("https://", self.article())

    def test_missing_is_explicit_blocker(self):
        result = prepare(self.source("![图](absent.png)"), self.output)
        self.assertEqual(result["images"][0]["kind"], "missing")
        self.assertIsNone(result["images"][0]["sha256"])
        self.assertFalse(result["ready_for_upload"])

    def test_absolute_parent_and_encoded_escape_paths_blocked(self):
        outside = self.root / "secret.png"
        outside.write_bytes(PNG)
        text = f"![a]({outside})\n![b](../secret.png)\n![c](%2E%2E%2Fsecret.png)\n![d](file:///etc/passwd)\n![e](C:/secret.png)"
        result = prepare(self.source(text), self.output)
        self.assertTrue(all(x["kind"] == "blocked" for x in result["images"]))
        self.assertTrue(all(x["relative_path"] is None for x in result["images"]))

    def test_symlink_outside_blocked(self):
        outside = self.root / "outside.png"
        outside.write_bytes(PNG)
        (self.source_dir / "alias.png").symlink_to(outside)
        result = prepare(self.source("![a](alias.png)"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertEqual(result["images"][0]["kind"], "blocked")

    def test_symlink_inside_is_safe(self):
        local = self.picture("sub/a.png")
        (self.source_dir / "alias.png").symlink_to(local)
        result = prepare(self.source("![a](alias.png)"), self.output)
        self.assertTrue(result["ready_for_upload"])

    def test_symlink_loop_is_explicit_blocker(self):
        (self.source_dir / "loop.png").symlink_to("loop.png")
        result = prepare(self.source("![a](loop.png)"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertEqual(result["images"][0]["kind"], "blocked")

    def test_html_img_explicit_blocker(self):
        result = prepare(self.source("<img src=\"image.png\" alt=\"x\">"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertTrue(any("html_img" in x for x in result["blocking_issues"]))

    def test_active_html_explicit_blocker(self):
        result = prepare(self.source("<script>not_executed()</script>"), self.output)
        self.assertFalse(result["ready_for_upload"])

    def test_other_html_and_frontmatter_blocked(self):
        result = prepare(self.source("---\ntitle: Metadata\n---\n<div onclick=\"bad()\">text</div>"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertTrue(any("frontmatter" in x for x in result["blocking_issues"]))
        self.assertTrue(any("raw_html" in x for x in result["blocking_issues"]))

    def test_undefined_and_malformed_image_fail_closed(self):
        result = prepare(self.source("![a][unknown]\n![b](file with spaces.png)\n![c"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertTrue(any("unresolved_image" in x for x in result["blocking_issues"]))

    def test_list_indent_ambiguity_fails_closed(self):
        result = prepare(self.source("- item\n    ![possibly a list image](x.png)"), self.output)
        self.assertFalse(result["ready_for_upload"])
        self.assertTrue(any("ambiguous_indented" in x for x in result["blocking_issues"]))

    def test_container_fence_fails_closed(self):
        result = prepare(self.source("> ```md\n> ![fake](x.png)\n> ```\n"), self.output)
        self.assertFalse(result["ready_for_upload"])

    def test_svg_and_unknown_files_not_copied(self):
        (self.source_dir / "a.svg").write_text("<svg><script>bad()</script></svg>")
        result = prepare(self.source("![a](a.svg)"), self.output)
        self.assertEqual(result["images"][0]["kind"], "blocked")
        self.assertFalse((self.output / "media").exists())

    def test_output_nonempty_refused_without_changes(self):
        self.output.mkdir()
        existing = self.output / "keep.txt"
        existing.write_text("keep")
        with self.assertRaises(PreparationError):
            prepare(self.source("new"), self.output)
        self.assertEqual(existing.read_text(), "keep")
        self.assertEqual(len(list(self.output.iterdir())), 1)

    def test_output_empty_allowed(self):
        self.output.mkdir()
        self.assertTrue(prepare(self.source("body"), self.output)["ready_for_upload"])

    def test_output_symlink_refused(self):
        real = self.root / "real"
        real.mkdir()
        self.output.symlink_to(real, target_is_directory=True)
        with self.assertRaises(PreparationError):
            prepare(self.source("body"), self.output)
        self.assertEqual(list(real.iterdir()), [])

    def test_output_parent_symlink_refused(self):
        real = self.root / "real"
        real.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(real, target_is_directory=True)
        with self.assertRaises(PreparationError):
            prepare(self.source("body"), alias / "child")

    def test_source_symlink_refused(self):
        source = self.source("body")
        alias = self.source_dir / "alias.md"
        alias.symlink_to(source)
        with self.assertRaises(PreparationError):
            prepare(alias, self.output)

    def test_reserved_tokens_refused(self):
        with self.assertRaises(PreparationError):
            prepare(self.source("{{RK_IMAGE_0001}}"), self.output)

    def test_wrong_extension_and_bad_txt_flag_refused(self):
        with self.assertRaises(PreparationError):
            prepare(self.source("x", "x.exe"), self.output)
        with self.assertRaises(PreparationError):
            prepare(self.source("x"), self.output, txt_as_markdown=True)

    def test_schema_and_hash_written(self):
        source = self.source("# Title\nbody\n")
        result = prepare(source, self.output)
        self.assertEqual(json.loads((self.output / "manifest.json").read_text()), result)
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(result["source"]["sha256"], hashlib.sha256(source.read_bytes()).hexdigest())
        self.assertEqual(result["baseline"]["prepared_markdown_sha256"], hashlib.sha256((self.output / "article.md").read_bytes()).hexdigest())

    def test_cli_blocked_exit_two_and_diagnostic_artifacts(self):
        source = self.source("![a](missing.png)")
        completed = subprocess.run([sys.executable, str(Path(__file__).with_name("prepare_text.py")), str(source), "--output", str(self.output)], capture_output=True, text=True)
        self.assertEqual(completed.returncode, 2, completed.stderr)
        self.assertFalse(json.loads(completed.stdout)["ready_for_upload"])
        self.assertTrue((self.output / "manifest.json").exists())

    @unittest.skipUnless(MarkdownIt, "Optional QA parser markdown-it-py is not a runtime dependency")
    def test_prepare_finalize_render_roundtrip(self):
        from finalize_images import finalize_bytes
        self.picture("a (1).png")
        original = '# 教程\n\n前文\n\n![图一](<a (1).png> "说明一")\n\n中间\n\n[![图二][ref]](https://example.invalid/)\n\n- 列表\n\n```md\n![不上传](missing.png)\n```\n\n![ref]\n\n[ref]: <a (1).png>\n  "说明二"\n'
        manifest = prepare(self.source(original), self.output)
        mapping = {image["placeholder"]: {"url": "https://native-upload.example/test/" + str(image["order"]) + ".png", "source_sha256": image["sha256"]} for image in manifest["images"]}
        finalized = finalize_bytes((self.output / "article.md").read_bytes(), manifest, mapping, self.output, ("native-upload.example",)).decode()
        parser = MarkdownIt("commonmark")

        def inspect(markdown):
            result = {"structure": [], "images": [], "code": []}
            for token in parser.parse(markdown):
                if token.type == "fence":
                    result["code"].append(token.content)
                if token.type != "inline":
                    result["structure"].append((token.type, token.tag))
                else:
                    for child in token.children or []:
                        if child.type == "image":
                            result["images"].append((child.content, child.attrGet("title"), child.attrGet("src")))
                        elif child.type == "text":
                            result["structure"].append(("text", child.content))
                        elif child.type in ("link_open", "link_close"):
                            result["structure"].append((child.type, child.attrGet("href")))
            return result

        before, after = inspect(original), inspect(finalized)
        self.assertEqual(len(after["images"]), 3)
        self.assertEqual([x[:2] for x in before["images"]], [x[:2] for x in after["images"]])
        self.assertEqual([x[2] for x in after["images"]], [x["url"] for x in mapping.values()])
        self.assertEqual(before["structure"], after["structure"])
        self.assertEqual(before["code"], after["code"])
        self.assertEqual(parser.render(finalized).count("<img "), 3)


if __name__ == "__main__":
    unittest.main()
