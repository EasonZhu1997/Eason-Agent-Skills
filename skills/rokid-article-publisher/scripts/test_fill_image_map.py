#!/usr/bin/env python3
"""Offline, synthetic tests; no real forum posts, accounts, or article content."""

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).with_name("fill_image_map.py")
SPEC = importlib.util.spec_from_file_location("fill_image_map", SCRIPT)
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)
ORIGIN = "https://forum.example.invalid"


def fixtures(count):
    manifest = {"schema_version": 1, "image_occurrences": count, "images": [{"order": i} for i in range(1, count + 1)]}
    uploads = {"schema_version": 1, "images": [{"order": i, "url": ORIGIN + "/native/image?id=" + str(i) + "&format=original"} for i in range(1, count + 1)]}
    template = '<h2>Author title</h2><p>A manual edit &amp; a <a href="https://reference.example.invalid/guide">link</a>.</p>'
    template += "".join('<img width="100%" src="{{IMAGE_' + str(i) + '}}" alt="Synthetic figure" style="height:auto;max-width:100%;"><p>Figure ' + str(i) + ': caption</p>' for i in range(1, count + 1))
    return template, manifest, uploads


class MappingTests(unittest.TestCase):
    def fill(self, template, manifest, uploads):
        return helper.fill_image_map(template, manifest, uploads, [ORIGIN])

    def test_counts_are_not_fixed(self):
        for count in (0, 1, 7, 31):
            with self.subTest(count=count):
                template, manifest, uploads = fixtures(count)
                output, audit = self.fill(template, manifest, uploads)
                self.assertEqual(audit["image_occurrences"], count)
                self.assertEqual(len(helper.scan_images(output)), count)
                self.assertNotIn("{{IMAGE_", output)

    def test_changes_only_intended_src_values(self):
        template, manifest, uploads = fixtures(2)
        template += '<pre><code>line one\n  line two &lt; value</code></pre><!-- keep this comment -->'
        output, audit = self.fill(template, manifest, uploads)
        expected = template
        for row in uploads["images"]:
            expected = expected.replace("{{IMAGE_" + str(row["order"]) + "}}", row["url"].replace("&", "&amp;"))
        self.assertEqual(output, expected)
        self.assertTrue(audit["only_placeholder_src_values_changed"])
        self.assertIn('href="https://reference.example.invalid/guide"', output)

    def test_single_quoted_and_leading_zero_placeholders(self):
        template, manifest, uploads = fixtures(1)
        template = template.replace('src="{{IMAGE_1}}"', "src='{{IMAGE_001}}'")
        output, _ = self.fill(template, manifest, uploads)
        self.assertEqual(helper.scan_images(output)[0]["src"], uploads["images"][0]["url"])

    def test_src_text_inside_other_quoted_attributes_is_not_modified(self):
        template, manifest, uploads = fixtures(1)
        for prefix in (
            "alt='example src=\"keep-me\"'",
            'alt="example src=\'keep-me\'"',
            'data-example="SRC = &quot;keep-me&quot;"',
            "title='a > b; src=\"leave-it\"'",
        ):
            with self.subTest(prefix=prefix):
                altered = template.replace('<img width="100%"', '<img ' + prefix + ' width="100%"')
                output, audit = self.fill(altered, manifest, uploads)
                self.assertIn(prefix, output)
                self.assertEqual(helper.scan_images(output)[0]["src"], uploads["images"][0]["url"])
                self.assertNotIn("{{IMAGE_", output)
                self.assertTrue(audit["only_placeholder_src_values_changed"])

    def test_attribute_name_matching_is_exact(self):
        template, manifest, uploads = fixtures(1)
        altered = template.replace('<img width="100%"', '<img data-src="keep-me" width="100%"')
        output, _ = self.fill(altered, manifest, uploads)
        self.assertIn('data-src="keep-me"', output)
        self.assertEqual(helper.scan_images(output)[0]["src"], uploads["images"][0]["url"])

    def test_missing_and_duplicate_uploads_are_rejected(self):
        template, manifest, uploads = fixtures(2)
        with self.assertRaises(helper.MappingError):
            self.fill(template, manifest, {"images": uploads["images"][:1]})
        with self.assertRaises(helper.MappingError):
            self.fill(template, manifest, {"images": uploads["images"] + uploads["images"][:1]})

    def test_duplicate_or_out_of_order_placeholders_are_rejected(self):
        template, manifest, uploads = fixtures(2)
        with self.assertRaises(helper.MappingError):
            self.fill(template.replace("{{IMAGE_2}}", "{{IMAGE_1}}"), manifest, uploads)
        swapped = template.replace("{{IMAGE_1}}", "temporary").replace("{{IMAGE_2}}", "{{IMAGE_1}}").replace("temporary", "{{IMAGE_2}}")
        with self.assertRaises(helper.MappingError):
            self.fill(swapped, manifest, uploads)

    def test_nested_images_are_rejected(self):
        template, manifest, uploads = fixtures(1)
        for wrapper in ("p", "div", "span"):
            with self.subTest(wrapper=wrapper):
                with self.assertRaisesRegex(helper.MappingError, "top-level"):
                    self.fill("<" + wrapper + ">" + template + "</" + wrapper + ">", manifest, uploads)

    def test_html_body_container_is_allowed(self):
        template, manifest, uploads = fixtures(1)
        output, _ = self.fill("<!doctype html><html><body>" + template + "</body></html>", manifest, uploads)
        self.assertIn("<img width=", output)

    def test_external_temporary_or_credential_urls_are_rejected(self):
        for url in ("https://another.example.invalid/image", "blob:temporary", "data:image/png;base64,AA==", "javascript:alert(1)", "https://name:secret@forum.example.invalid/image"):
            with self.subTest(url=url):
                template, manifest, uploads = fixtures(1)
                uploads["images"][0]["url"] = url
                with self.assertRaises(helper.MappingError):
                    self.fill(template, manifest, uploads)

    def test_existing_native_image_is_untouched(self):
        template, manifest, uploads = fixtures(1)
        existing = '<img src="' + ORIGIN + '/native/existing.png" width="180" alt="Existing manual image">'
        output, audit = self.fill(existing + template, manifest, uploads)
        self.assertTrue(output.startswith(existing))
        self.assertEqual(audit["existing_images_preserved"], 1)

    def test_wrong_placeholders_and_srcset_fail(self):
        template, manifest, uploads = fixtures(1)
        with self.assertRaises(helper.MappingError):
            self.fill(template + "<p>{{IMAGE_1}}</p>", manifest, uploads)
        with self.assertRaises(helper.MappingError):
            self.fill(template.replace('<img width=', '<img srcset="unreviewed" width='), manifest, uploads)

    def test_repeated_source_media_may_share_native_url(self):
        template, manifest, uploads = fixtures(2)
        uploads["images"][1]["url"] = uploads["images"][0]["url"]
        output, audit = self.fill(template, manifest, uploads)
        self.assertEqual(audit["image_occurrences"], 2)
        self.assertEqual(helper.scan_images(output)[0]["src"], helper.scan_images(output)[1]["src"])

    def test_cli_and_nonempty_output_refusal(self):
        with tempfile.TemporaryDirectory(prefix="forum-map-test-") as directory:
            base = Path(directory)
            template, manifest, uploads = fixtures(2)
            (base / "template.html").write_text(template)
            (base / "manifest.json").write_text(json.dumps(manifest))
            (base / "uploads.json").write_text(json.dumps(uploads))
            out = base / "result"
            command = [sys.executable, str(SCRIPT), "--template", str(base / "template.html"), "--manifest", str(base / "manifest.json"), "--uploads", str(base / "uploads.json"), "--allowed-origin", ORIGIN, "--out", str(out)]
            first = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = (out / "article.html").read_bytes()
            second = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(second.returncode, 2)
            self.assertEqual((out / "article.html").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
