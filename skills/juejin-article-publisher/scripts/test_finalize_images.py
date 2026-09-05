#!/usr/bin/env python3
"""Offline regression tests. All image bytes and URLs below are synthetic."""

import contextlib
import copy
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from finalize_images import ValidationError, finalize_bytes, main, read_json, validate_url


class FinalizeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "media").mkdir()
        self.manifest = {"schema_version": 1, "blocking_issues": [], "images": []}
        self.mapping = {}
        for n, data in enumerate((b"synthetic first image", b"synthetic second image"), 1):
            digest = hashlib.sha256(data).hexdigest()
            relative = "media/%s.png" % digest
            (self.root / relative).write_bytes(data)
            key = "{{JJ_IMAGE_%04d}}" % n
            self.manifest["images"].append({"order": n, "placeholder": key, "kind": "local", "relative_path": relative, "sha256": digest, "alt": "图"})
            self.mapping[key] = {"url": "https://p3-juejin.byteimg.com/tos-cn-i-test/image-%d.png?signature=EXAMPLE%%2B%%2F&expires=123" % n, "source_sha256": digest}
        self.article = "# 原标题\r\n\r\n![图一]({{JJ_IMAGE_0001}})\r\n\r\n```js\r\n  const x = '\\n'; // 原缩进\r\n```\r\n![图二]({{JJ_IMAGE_0002}})\r\n正文不变。\r\n".encode()
        self.manifest["baseline"] = {"prepared_markdown_sha256": hashlib.sha256(self.article).hexdigest()}

    def tearDown(self):
        self.temp.cleanup()

    def finalize(self, article=None, manifest=None, mapping=None, hosts=()):
        return finalize_bytes(self.article if article is None else article, self.manifest if manifest is None else manifest, self.mapping if mapping is None else mapping, self.root, hosts)

    def reject(self, **kwargs):
        with self.assertRaises(ValidationError):
            self.finalize(**kwargs)

    def test_preserves_all_other_bytes_and_signed_query(self):
        expected = self.article
        for key, entry in self.mapping.items():
            expected = expected.replace(key.encode(), entry["url"].encode())
        self.assertEqual(self.finalize(), expected)

    def test_mapping_insertion_order_is_irrelevant(self):
        self.assertEqual(self.finalize(mapping=dict(reversed(list(self.mapping.items())))), self.finalize())

    def test_zero_images_keeps_article_exactly(self):
        article = b"Plain\r\ntext"
        manifest = {"schema_version": 1, "blocking_issues": [], "images": [], "baseline": {"prepared_markdown_sha256": hashlib.sha256(article).hexdigest()}}
        self.assertEqual(self.finalize(article=article, manifest=manifest, mapping={}), article)

    def test_missing_invalid_and_incorrect_prepared_baseline(self):
        for baseline in (None, [], {}, {"prepared_markdown_sha256": None}, {"prepared_markdown_sha256": "not-a-sha256"}, {"prepared_markdown_sha256": "0" * 64}):
            with self.subTest(baseline=baseline):
                manifest = copy.deepcopy(self.manifest)
                manifest["baseline"] = baseline
                self.reject(manifest=manifest)
        manifest = copy.deepcopy(self.manifest)
        del manifest["baseline"]
        self.reject(manifest=manifest)

    def test_modified_body_or_code_context_rejected(self):
        for article in (
            self.article.replace("原标题".encode(), "改标题".encode()),
            b"````markdown\n" + self.article + b"\n````\n",
            self.article.replace(b"\r\n", b"\n"),
            self.article + b"\nAdditional text.\n",
        ):
            with self.subTest(article=article), self.assertRaisesRegex(ValidationError, "changed after preparation"):
                self.finalize(article=article)

    def test_optional_sha(self):
        for value in self.mapping.values():
            del value["source_sha256"]
        self.finalize()

    def test_duplicate_source_may_share_url(self):
        first = self.manifest["images"][0]
        self.manifest["images"][1].update({k: first[k] for k in ("sha256", "relative_path")})
        self.mapping["{{JJ_IMAGE_0002}}"] = copy.deepcopy(self.mapping["{{JJ_IMAGE_0001}}"])
        self.finalize()

    def test_different_sources_cannot_share_url(self):
        self.mapping["{{JJ_IMAGE_0002}}"]["url"] = self.mapping["{{JJ_IMAGE_0001}}"]["url"]
        self.reject()

    def test_missing_extra_and_mismatched_maps(self):
        for mode in ("missing", "extra", "sha", "field", "string"):
            with self.subTest(mode=mode):
                mapping = copy.deepcopy(self.mapping)
                if mode == "missing":
                    del mapping["{{JJ_IMAGE_0001}}"]
                elif mode == "extra":
                    mapping["extra"] = {}
                elif mode == "sha":
                    mapping["{{JJ_IMAGE_0001}}"]["source_sha256"] = "0" * 64
                elif mode == "field":
                    mapping["{{JJ_IMAGE_0001}}"]["unknown"] = True
                else:
                    mapping["{{JJ_IMAGE_0001}}"] = "https://juejin.cn/test.png"
                self.reject(mapping=mapping)

    def test_missing_duplicate_malformed_and_reordered_placeholders(self):
        for article in (
            self.article.replace(b"{{JJ_IMAGE_0001}}", b""),
            self.article + b"{{JJ_IMAGE_0001}}",
            self.article + b"{{JJ_IMAGE_oops}}",
            self.article.replace(b"0001", b"swap").replace(b"0002", b"0001").replace(b"swap", b"0002"),
        ):
            with self.subTest(article=article):
                # Keep this test focused on placeholder structure rather than
                # letting the earlier article hash check hide a regression.
                manifest = copy.deepcopy(self.manifest)
                manifest["baseline"]["prepared_markdown_sha256"] = hashlib.sha256(article).hexdigest()
                self.reject(article=article, manifest=manifest)

    def test_blocker_and_incomplete_manifest(self):
        for field, value in (("blocking_issues", ["Remote image unresolved"]), ("blocking_issues", None), ("schema_version", 2), ("schema_version", True), ("images", {})):
            manifest = copy.deepcopy(self.manifest)
            manifest[field] = value
            self.reject(manifest=manifest)

    def test_local_image_requirements(self):
        for field, value in (("kind", "remote"), ("sha256", None), ("order", 2), ("order", True), ("placeholder", "{{JJ_IMAGE_0002}}"), ("relative_path", "../outside.png"), ("relative_path", "/outside.png"), ("relative_path", "media\\image.png"), ("relative_path", "media/missing.png")):
            with self.subTest(field=field, value=value):
                manifest = copy.deepcopy(self.manifest)
                manifest["images"][0][field] = value
                self.reject(manifest=manifest)

    def test_modified_image_rejected(self):
        (self.root / self.manifest["images"][0]["relative_path"]).write_bytes(b"changed")
        self.reject()

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            path = Path(outside) / "image.png"
            path.write_bytes(b"outside")
            link = self.root / "media/escape.png"
            link.symlink_to(path)
            self.manifest["images"][0].update(relative_path="media/escape.png", sha256=hashlib.sha256(b"outside").hexdigest())
            self.reject()

    def test_url_rejections(self):
        invalid = (
            "http://p3-juejin.byteimg.com/image.png",
            "data:image/png;base64,test", "file:///image.png", "blob:https://juejin.cn/test", "javascript:alert(1)",
            "https://user:password@juejin.cn/image.png", "https://juejin.cn:444/image.png",
            "https://juejin.cn.evil.example/image.png", "https://eviljuejin.cn/image.png",
            "https://byteimg.com.evil.example/image.png", "https://juejin.cn./image.png",
            "https://juejin.cn/", "https://juejin.cn/image.png\nSECRET", " https://juejin.cn/image.png",
            "https://juejin.cn/image.png\"<script>", "https://juejin.cn/image.png)injection",
            "https://juejin.cn/image.png\u2028EXAMPLE",
            "https://juejin.cn\\@evil.example/image.png", "https://[::1]/image.png",
            "https://juejin.cn:notaport/image.png",
        )
        for url in invalid:
            with self.subTest(url=url), self.assertRaises(ValidationError) as caught:
                validate_url(url)
            self.assertNotIn(url, str(caught.exception))

    def test_url_defaults_and_explicit_host(self):
        for url in ("https://juejin.cn/image.png", "https://p3-juejin.byteimg.com:443/image.png", "https://assets.juejin.cn/path/image.png?signature=EXAMPLE%2B%2F&x=1"):
            self.assertEqual(validate_url(url), url)
        self.mapping["{{JJ_IMAGE_0001}}"]["url"] = "https://image-cdn.example/image.png"
        self.reject()
        self.finalize(hosts=("image-cdn.example",))
        for host in ("*.example", "https://image-cdn.example", "IMAGE-CDN.EXAMPLE", "image-cdn.example:443"):
            self.reject(hosts=(host,))

    def test_duplicate_json_keys_rejected(self):
        for value in ('{"x": 1, "x": 2}', '{"x": {"url": "a", "url": "b"}}'):
            path = self.root / "duplicate.json"
            path.write_text(value)
            with self.assertRaises(ValidationError):
                read_json(path)

    def run_cli(self, outname="final.md"):
        (self.root / "manifest.json").write_text(json.dumps(self.manifest))
        (self.root / "hosted-map.json").write_text(json.dumps(self.mapping))
        (self.root / "article.md").write_bytes(self.article)
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            status = main(["--manifest", str(self.root / "manifest.json"), "--article", str(self.root / "article.md"), "--hosted-map", str(self.root / "hosted-map.json"), "--output", str(self.root / outname)])
        return status, stdout.getvalue(), stderr.getvalue()

    def test_cli_no_signed_url_in_output_and_no_overwrite(self):
        status, stdout, stderr = self.run_cli()
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(stdout)["images"], 2)
        self.assertEqual(stderr, "")
        self.assertNotIn("signature", stdout)
        expected = (self.root / "final.md").read_bytes()
        status, _, stderr = self.run_cli()
        self.assertEqual(status, 2)
        self.assertIn("already exists", stderr)
        self.assertEqual((self.root / "final.md").read_bytes(), expected)

    def test_cli_error_is_prewrite_and_does_not_leak(self):
        self.mapping["{{JJ_IMAGE_0002}}"]["url"] = "https://untrusted.example/image.png?signature=PRIVATE_EXAMPLE"
        status, stdout, stderr = self.run_cli()
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertNotIn("PRIVATE_EXAMPLE", stderr)
        self.assertFalse((self.root / "final.md").exists())
        self.assertFalse(list(self.root.glob(".juejin-finalize-*")))

    def test_cli_changed_article_refuses_output(self):
        self.article = b"````markdown\n" + self.article + b"\n````\n"
        status, stdout, stderr = self.run_cli()
        self.assertEqual(status, 2)
        self.assertEqual(stdout, "")
        self.assertIn("changed after preparation", stderr)
        self.assertFalse((self.root / "final.md").exists())


if __name__ == "__main__":
    unittest.main()
