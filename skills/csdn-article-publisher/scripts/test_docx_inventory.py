#!/usr/bin/env python3
"""Synthetic, account-free standard-library tests for docx_inventory.py."""

import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from xml.sax.saxutils import escape, quoteattr
from zipfile import ZipFile
import zlib


SCRIPT = Path(__file__).with_name("docx_inventory.py")
SPEC = importlib.util.spec_from_file_location("docx_inventory", SCRIPT)
inventory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(inventory)

NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
)
IMAGE_TYPE = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"


def png(width=2, height=3):
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data) & 0xffffffff)
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    pixels = (b"\0" + b"\xff\xff\xff" * width) * height
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b"")


def jpeg(width=7, height=5):
    # Minimal SOF header sufficient for size inspection; no external image library.
    sof = b"\x08" + struct.pack(">HH", height, width) + b"\x01\x01\x11\x00"
    return b"\xff\xd8\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof + b"\xff\xd9"


def paragraph(text):
    return "<w:p><w:r><w:t>" + escape(text) + "</w:t></w:r></w:p>"


def picture(rel_id, floating=False):
    tag = "anchor" if floating else "inline"
    return '<w:p><w:r><w:drawing><wp:' + tag + '><a:blip r:embed=' + quoteattr(rel_id) + '/></wp:' + tag + '></w:drawing></w:r></w:p>'


def write_docx(path, body, relationships, media=None, extra_members=None):
    rels = []
    for rel_id, target, *mode in relationships:
        attrs = {"Id": rel_id, "Type": IMAGE_TYPE, "Target": target}
        if mode:
            attrs["TargetMode"] = mode[0]
        rels.append("<Relationship " + " ".join(key + "=" + quoteattr(value) for key, value in attrs.items()) + "/>")
    with ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", '<w:document ' + NS + '><w:body>' + body + '</w:body></w:document>')
        zf.writestr("word/_rels/document.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(rels) + '</Relationships>')
        for name, data in (media or {}).items():
            zf.writestr(name, data)
        for name, data in (extra_members or {}).items():
            zf.writestr(name, data)


class InventoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="docx-inventory-test-")
        self.base = Path(self.temp.name)
        self.source = self.base / "synthetic.docx"
        self.out = self.base / "output"

    def tearDown(self):
        self.temp.cleanup()

    def test_repeated_media_preserves_occurrences_and_context(self):
        data = png(4, 6)
        body = paragraph("Introduction") + picture("r1") + paragraph("图｜First picture") + paragraph("Second section") + picture("r2") + paragraph("图｜Repeated picture")
        write_docx(self.source, body, [("r1", "media/a.png"), ("r2", "media/a.png")], {"word/media/a.png": data})
        result = inventory.build_inventory(self.source, self.out)
        self.assertEqual(result["image_occurrences"], 2)
        self.assertEqual(result["unique_media"], 1)
        self.assertEqual([i["order"] for i in result["images"]], [1, 2])
        self.assertEqual([i["paragraph_index"] for i in result["images"]], [1, 4])
        self.assertEqual(result["images"][0]["caption"], "图｜First picture")
        self.assertEqual(result["images"][1]["caption"], "图｜Repeated picture")
        self.assertEqual(result["images"][0]["preceding_text"], ["Introduction"])
        self.assertEqual(result["images"][0]["following_text"][0], "图｜First picture")
        self.assertEqual(result["images"][0]["relative_path"], result["images"][1]["relative_path"])
        self.assertEqual((result["images"][0]["width"], result["images"][0]["height"]), (4, 6))
        self.assertEqual(len(list((self.out / "media").iterdir())), 1)
        self.assertEqual((self.out / result["images"][0]["relative_path"]).read_bytes(), data)
        self.assertEqual(set(result["source"]), {"filename", "sha256"})
        self.assertEqual(result["source"]["filename"], "synthetic.docx")
        self.assertNotIn(str(self.base), (self.out / "manifest.json").read_text())

    def test_no_fixed_image_count(self):
        for count in (0, 1, 31):
            with self.subTest(count=count):
                source = self.base / ("count-" + str(count) + ".docx")
                out = self.base / ("count-" + str(count))
                write_docx(source, "".join(picture("r1") for _ in range(count)), [("r1", "media/a.png")], {"word/media/a.png": png()})
                result = inventory.build_inventory(source, out)
                self.assertEqual(result["image_occurrences"], count)
                self.assertEqual(result["unique_media"], 1 if count else 0)

    def test_table_images_follow_body_reading_order(self):
        table = '<w:tbl><w:tr><w:tc>' + paragraph("Cell text") + picture("r2") + paragraph("图｜Table image") + '</w:tc></w:tr></w:tbl>'
        body = picture("r1") + table + picture("r1")
        write_docx(self.source, body, [("r1", "media/a.png"), ("r2", "media/b.jpg")], {"word/media/a.png": png(), "word/media/b.jpg": jpeg(13, 11)})
        result = inventory.build_inventory(self.source, self.out)
        self.assertEqual([i["paragraph_index"] for i in result["images"]], [0, 2, 4])
        self.assertEqual((result["images"][1]["width"], result["images"][1]["height"]), (13, 11))
        self.assertEqual(result["images"][1]["caption"], "图｜Table image")

    def test_missing_null_and_external_references_are_not_valid_images(self):
        body = "".join(picture(rel) for rel in ("good", "dangling", "null", "missing", "external"))
        write_docx(self.source, body, [("good", "media/a.png"), ("null", "../NULL"), ("missing", "media/absent.png"), ("external", "https://example.invalid/image.png?token=synthetic", "External")], {"word/media/a.png": png()})
        result = inventory.build_inventory(self.source, self.out)
        self.assertEqual(result["image_occurrences"], 1)
        codes = {w["code"] for w in result["warnings"]}
        self.assertTrue({"dangling_image_reference", "null_image_target", "missing_image_part", "external_image_reference"} <= codes)
        serialized = json.dumps(result)
        self.assertNotIn("token=", serialized)
        self.assertNotIn("example.invalid", serialized)

    def test_floating_image_warning(self):
        write_docx(self.source, picture("r1", floating=True), [("r1", "media/a.png")], {"word/media/a.png": png()})
        result = inventory.build_inventory(self.source, self.out)
        self.assertEqual(result["image_occurrences"], 1)
        self.assertIn("floating_image", {w["code"] for w in result["warnings"]})

    def test_nonempty_existing_output_is_refused(self):
        write_docx(self.source, picture("r1"), [("r1", "media/a.png")], {"word/media/a.png": png()})
        self.out.mkdir()
        sentinel = self.out / "keep.txt"
        sentinel.write_text("must remain")
        with self.assertRaisesRegex(inventory.InventoryError, "not empty"):
            inventory.build_inventory(self.source, self.out)
        self.assertEqual(sentinel.read_text(), "must remain")
        self.assertFalse((self.out / "media").exists())

    def test_existing_empty_output_is_allowed(self):
        write_docx(self.source, paragraph("No images"), [])
        self.out.mkdir()
        self.assertEqual(inventory.build_inventory(self.source, self.out)["image_occurrences"], 0)

    def test_malicious_zip_paths_are_rejected_before_writes(self):
        for member in ("../outside.txt", "/tmp/outside.txt", "word/../../escape.txt", "word\\media\\bad.png", "C:/absolute.txt"):
            with self.subTest(member=member):
                write_docx(self.source, paragraph("Safe text"), [], extra_members={member: b"untrusted"})
                with self.assertRaisesRegex(inventory.InventoryError, "Unsafe ZIP"):
                    inventory.build_inventory(self.source, self.out)
                self.assertFalse(self.out.exists())

    def test_malicious_relationship_targets_are_skipped(self):
        outside = self.base / "outside.png"
        outside.write_bytes(png(17, 19))
        targets = ("../../outside.png", "%2e%2e/%2e%2e/outside.png", "/absolute.png", "..\\..\\outside.png", "file:///outside.png", "http://[")
        rels = [("r" + str(i), target) for i, target in enumerate(targets)]
        write_docx(self.source, "".join(picture(rel[0]) for rel in rels), rels)
        result = inventory.build_inventory(self.source, self.out)
        self.assertEqual(result["image_occurrences"], 0)
        self.assertEqual(list((self.out / "media").iterdir()), [])
        self.assertEqual(outside.read_bytes(), png(17, 19))
        self.assertTrue(all(w["code"] in ("unsafe_image_target", "external_image_reference") for w in result["warnings"]))

    def test_unknown_dimensions_use_null_and_warning(self):
        write_docx(self.source, picture("r1"), [("r1", "media/a.webp")], {"word/media/a.webp": b"synthetic-unsupported-image-header"})
        result = inventory.build_inventory(self.source, self.out)
        self.assertIsNone(result["images"][0]["width"])
        self.assertIsNone(result["images"][0]["height"])
        self.assertIn("unknown_image_dimensions", {w["code"] for w in result["warnings"]})

    def test_identical_bytes_in_different_parts_are_deduplicated(self):
        data = png()
        write_docx(self.source, picture("r1") + picture("r2"), [("r1", "media/a.png"), ("r2", "media/b.png")], {"word/media/a.png": data, "word/media/b.png": data})
        result = inventory.build_inventory(self.source, self.out)
        self.assertEqual(result["image_occurrences"], 2)
        self.assertEqual(result["unique_media"], 1)
        self.assertEqual(result["images"][0]["sha256"], hashlib.sha256(data).hexdigest())

    def test_alternate_fallback_is_not_a_second_picture(self):
        choice = '<mc:AlternateContent><mc:Choice Requires="a">' + picture("r1") + '</mc:Choice><mc:Fallback>' + picture("r1") + '</mc:Fallback></mc:AlternateContent>'
        write_docx(self.source, choice, [("r1", "media/a.png")], {"word/media/a.png": png()})
        self.assertEqual(inventory.build_inventory(self.source, self.out)["image_occurrences"], 1)

    def test_alternate_uses_available_fallback(self):
        choice = '<mc:AlternateContent><mc:Choice Requires="a">' + picture("missing") + '</mc:Choice><mc:Fallback>' + picture("r1") + '</mc:Fallback></mc:AlternateContent>'
        write_docx(self.source, choice, [("r1", "media/a.png")], {"word/media/a.png": png()})
        self.assertEqual(inventory.build_inventory(self.source, self.out)["image_occurrences"], 1)

    def test_cli_writes_expected_schema(self):
        write_docx(self.source, picture("r1"), [("r1", "media/a.png")], {"word/media/a.png": png()})
        run = subprocess.run([sys.executable, str(SCRIPT), "--source", str(self.source), "--out", str(self.out)], text=True, capture_output=True, check=False)
        self.assertEqual(run.returncode, 0, run.stderr)
        result = json.loads((self.out / "manifest.json").read_text())
        self.assertEqual(set(result), {"schema_version", "source", "image_occurrences", "unique_media", "images", "warnings"})
        self.assertEqual(result["schema_version"], 1)
        self.assertEqual(set(result["images"][0]), {"order", "paragraph_index", "relative_path", "sha256", "width", "height", "caption", "preceding_text", "following_text"})
        again = subprocess.run([sys.executable, str(SCRIPT), "--source", str(self.source), "--out", str(self.out)], text=True, capture_output=True, check=False)
        self.assertEqual(again.returncode, 2)
        self.assertIn("not empty", again.stderr)


if __name__ == "__main__":
    unittest.main()
