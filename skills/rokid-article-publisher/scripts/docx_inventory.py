#!/usr/bin/env python3
"""Inventory and safely extract embedded DOCX images, using Python's standard library.

Usage: python3 docx_inventory.py --source article.docx --out new-output-directory

The output contains manifest.json and content-addressed files in media/. Paragraph
indices are zero-based XML reading order, including paragraphs inside table cells.
Floating images are reported in anchor order, which is not guaranteed to equal their
visual page position. Captions are candidates to verify against the article editor.
No network requests are made. The input document is never modified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import struct
import sys
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile


W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
WP = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
V = "{urn:schemas-microsoft-com:vml}"
O = "{urn:schemas-microsoft-com:office:office}"
MC = "{http://schemas.openxmlformats.org/markup-compatibility/2006}"
IMAGE_TAGS = {A + "blip", V + "imagedata"}
MAX_MEMBERS = 10000
MAX_MEMBER_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_XML_BYTES = 32 * 1024 * 1024
CONTEXT_COUNT = 3
CAPTION_RE = re.compile(
    r"^\s*(?:图(?:\s*\d+(?:[.-]\d+)*|\s*[一二三四五六七八九十百]+)?"
    r"\s*[|｜:：、.。—-]|图\s+\d+\b|(?:Figure|Fig\.?)\s+\d+\b)",
    re.IGNORECASE,
)


class InventoryError(Exception):
    """A source or output safety condition prevents creating an inventory."""


def _warning(warnings, code, message, paragraph_index=None, relationship_id=None):
    record = {"code": code, "message": message}
    if paragraph_index is not None:
        record["paragraph_index"] = paragraph_index
    if relationship_id:
        record["relationship_id"] = relationship_id
    warnings.append(record)


def _check_output_directory(path: Path):
    # Reject a symlink itself even when it points at an empty directory.
    if path.is_symlink():
        raise InventoryError("Output directory must not be a symbolic link.")
    if path.exists():
        if not path.is_dir():
            raise InventoryError("Output path already exists and is not a directory.")
        if any(path.iterdir()):
            raise InventoryError("Output directory is not empty; choose a new directory.")


def _validate_zip(zf: ZipFile):
    entries = zf.infolist()
    if len(entries) > MAX_MEMBERS:
        raise InventoryError("DOCX has too many ZIP members.")
    total = 0
    seen = set()
    for entry in entries:
        name = entry.filename
        parts = name.rstrip("/").split("/")
        if (
            not name
            or "\x00" in name
            or "\\" in name
            or name.startswith("/")
            or re.match(r"^[A-Za-z]:", name)
            or any(part in ("..", ".", "") for part in parts)
        ):
            raise InventoryError("Unsafe ZIP member path; no files were extracted.")
        if name in seen:
            raise InventoryError("Duplicate ZIP member name; the archive is ambiguous.")
        seen.add(name)
        if stat.S_ISLNK(entry.external_attr >> 16):
            raise InventoryError("Symbolic links are not allowed inside a DOCX archive.")
        if entry.flag_bits & 1:
            raise InventoryError("Encrypted ZIP members are not supported.")
        if entry.file_size > MAX_MEMBER_BYTES:
            raise InventoryError("A DOCX member exceeds the extraction size limit.")
        total += entry.file_size
        if total > MAX_TOTAL_BYTES:
            raise InventoryError("DOCX exceeds the total extraction size limit.")


def _read_member(zf: ZipFile, name: str, limit=MAX_MEMBER_BYTES) -> bytes:
    try:
        info = zf.getinfo(name)
    except KeyError as exc:
        raise InventoryError("Required DOCX part is missing: " + name) from exc
    if info.file_size > limit:
        raise InventoryError("DOCX part exceeds the permitted size: " + name)
    with zf.open(info) as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise InventoryError("DOCX part exceeds the permitted size: " + name)
    return data


def _parse_xml(data: bytes, part_name: str):
    # Word parts do not need DTDs or entities. Reject them rather than expanding.
    if re.search(br"<!\s*(?:DOCTYPE|ENTITY)\b", data.replace(b"\x00", b""), re.IGNORECASE):
        raise InventoryError("DTD or entity declaration is not allowed in " + part_name)
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise InventoryError("Invalid XML in " + part_name) from exc


def _resolve_target(target: str):
    """Return (ZIP member name, error code), never a filesystem path."""
    if not target or target.strip().upper() == "NULL":
        return None, "null_image_target"
    # OPC targets are URI paths. Decode before evaluating traversal attempts.
    decoded = unquote(target)
    if "\x00" in decoded or "\\" in decoded:
        return None, "unsafe_image_target"
    try:
        parsed = urlsplit(decoded)
    except ValueError:
        return None, "unsafe_image_target"
    if parsed.scheme or parsed.netloc:
        return None, "external_image_reference"
    if parsed.query or parsed.fragment:
        return None, "unsafe_image_target"
    path = parsed.path
    if path.startswith("/") or re.match(r"^[A-Za-z]:", path):
        return None, "unsafe_image_target"
    components = ["word"]
    for part in path.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            if not components:
                return None, "unsafe_image_target"
            components.pop()
        else:
            components.append(part)
    if not components or components[-1].upper() == "NULL":
        return None, "null_image_target"
    return "/".join(components), None


def image_dimensions(data: bytes):
    """Return (width, height, canonical extension), or nullable dimensions."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        if len(data) >= 24 and data[12:16] == b"IHDR":
            width, height = struct.unpack(">II", data[16:24])
            if width and height:
                return width, height, ".png"
        return None, None, ".png"
    if data.startswith(b"\xff\xd8"):
        pos = 2
        # SOF markers holding size, excluding Huffman and arithmetic coding tables.
        sof = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while pos < len(data):
            if data[pos] != 0xFF:
                return None, None, ".jpg"
            while pos < len(data) and data[pos] == 0xFF:
                pos += 1
            if pos >= len(data):
                break
            marker = data[pos]
            pos += 1
            if marker in (0xD9, 0xDA):
                break
            if marker in (0x01, 0xD8) or 0xD0 <= marker <= 0xD7:
                continue
            if pos + 2 > len(data):
                break
            size = struct.unpack(">H", data[pos:pos + 2])[0]
            if size < 2 or pos + size > len(data):
                break
            if marker in sof and size >= 7:
                height, width = struct.unpack(">HH", data[pos + 3:pos + 7])
                if width and height:
                    return width, height, ".jpg"
                break
            pos += size
        return None, None, ".jpg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        if len(data) >= 10:
            width, height = struct.unpack("<HH", data[6:10])
            if width and height:
                return width, height, ".gif"
        return None, None, ".gif"
    if data.startswith(b"BM") and len(data) >= 26:
        header_size = struct.unpack("<I", data[14:18])[0]
        if header_size == 12:
            width, height = struct.unpack("<HH", data[18:22])
        elif header_size >= 40:
            width, height = struct.unpack("<ii", data[18:26])
            height = abs(height)
        else:
            width = height = 0
        if width > 0 and height > 0:
            return width, height, ".bmp"
    return None, None, None


def _image_reference(node):
    return node.get(R + "embed") or node.get(R + "id") or node.get(O + "relid") or node.get(R + "link")


def _branch_has_embedded_image(branch, relationships, members):
    for node in branch.iter():
        if node.tag not in IMAGE_TAGS:
            continue
        rel = relationships.get(_image_reference(node))
        if not rel or rel.get("TargetMode", "").lower() == "external":
            continue
        target, problem = _resolve_target(rel.get("Target", ""))
        if not problem and target in members:
            return True
    return False


def _logical_children(node, relationships, members):
    # An AlternateContent fallback is another representation of one object,
    # not a second picture. Prefer a branch with an available embedded asset.
    if node.tag == MC + "AlternateContent":
        branches = [c for c in node if c.tag in (MC + "Choice", MC + "Fallback")]
        preferred = next((c for c in branches if _branch_has_embedded_image(c, relationships, members)), None)
        return [preferred if preferred is not None else branches[0]] if branches else []
    return list(node)


def _logical_walk(node, relationships, members):
    yield node
    for child in _logical_children(node, relationships, members):
        yield from _logical_walk(child, relationships, members)


def _paragraph_nodes(paragraph, relationships, members):
    """Traverse one paragraph, excluding text belonging to nested text-box paragraphs."""
    for child in _logical_children(paragraph, relationships, members):
        if child.tag == W + "p":
            continue
        yield child
        yield from _paragraph_nodes(child, relationships, members)


def _paragraph_text(paragraph, relationships, members):
    chunks = []
    for node in _paragraph_nodes(paragraph, relationships, members):
        if node.tag == W + "t":
            chunks.append(node.text or "")
        elif node.tag == W + "tab":
            chunks.append("\t")
        elif node.tag in (W + "br", W + "cr") and node.get(W + "type", "textWrapping") == "textWrapping":
            chunks.append("\n")
    return "".join(chunks).strip()


def _is_floating(node, paragraph, parents):
    current = node
    while current is not None and current is not paragraph:
        if current.tag == WP + "anchor":
            return True
        if current.tag in (V + "shape", V + "group") and re.search(
            r"(?:^|;)\s*position\s*:\s*absolute(?:\s*;|\s*$)",
            current.get("style", ""),
            re.IGNORECASE,
        ):
            return True
        current = parents.get(current)
    return False


def _caption_candidate(index, texts):
    nearby = []
    if CAPTION_RE.match(texts[index]):
        nearby.append((0, 0, texts[index]))
    previous = [(i, text) for i, text in enumerate(texts[:index]) if text][-CONTEXT_COUNT:]
    following = [(i, texts[i]) for i in range(index + 1, len(texts)) if texts[i]][:CONTEXT_COUNT]
    for i, text in previous + following:
        if CAPTION_RE.match(text):
            nearby.append((abs(i - index), 0 if i > index else 1, text))
    return min(nearby)[2] if nearby else None


def build_inventory(source: Path, out: Path):
    """Create out/manifest.json and out/media. Return the manifest dictionary."""
    source = Path(source)
    out = Path(out)
    _check_output_directory(out)
    if not source.is_file():
        raise InventoryError("Source DOCX does not exist or is not a regular file.")
    warnings = []
    images = []
    payloads = {}
    members_cache = {}
    try:
        with source.open("rb") as source_stream:
            source_hash = hashlib.file_digest(source_stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else None
            if source_hash is None:
                source_stream.seek(0)
                digest = hashlib.sha256()
                for chunk in iter(lambda: source_stream.read(1024 * 1024), b""):
                    digest.update(chunk)
                source_hash = digest.hexdigest()
            source_stream.seek(0)
            with ZipFile(source_stream) as zf:
                _validate_zip(zf)
                members = set(zf.namelist())
                root = _parse_xml(_read_member(zf, "word/document.xml", MAX_XML_BYTES), "word/document.xml")
                relationships = {}
                rel_path = "word/_rels/document.xml.rels"
                if rel_path in members:
                    rel_root = _parse_xml(_read_member(zf, rel_path, MAX_XML_BYTES), rel_path)
                    for rel in rel_root:
                        rel_id = rel.get("Id")
                        if rel_id in relationships:
                            raise InventoryError("Duplicate relationship ID in the document.")
                        if rel_id:
                            relationships[rel_id] = dict(rel.attrib)
                body = root.find(W + "body")
                if body is None:
                    raise InventoryError("DOCX document body is missing.")
                parents = {child: parent for parent in root.iter() for child in parent}
                paragraphs = [n for n in _logical_walk(body, relationships, members) if n.tag == W + "p"]
                texts = [_paragraph_text(p, relationships, members) for p in paragraphs]
                for index, paragraph in enumerate(paragraphs):
                    for node in _paragraph_nodes(paragraph, relationships, members):
                        if node.tag not in IMAGE_TAGS:
                            continue
                        rel_id = _image_reference(node)
                        if _is_floating(node, paragraph, parents):
                            _warning(warnings, "floating_image", "Image is floating; paragraph anchor order may differ from visual page position.", index, rel_id)
                        if node.get(R + "link") and node.get(R + "embed"):
                            _warning(warnings, "linked_image_has_embedded_copy", "A linked image also has an embedded copy; only the embedded bytes are used.", index, rel_id)
                        if not rel_id:
                            _warning(warnings, "missing_image_reference", "Image has no supported embedded relationship; it was not extracted.", index)
                            continue
                        rel = relationships.get(rel_id)
                        if rel is None:
                            _warning(warnings, "dangling_image_reference", "Image relationship is absent; it was not counted as a valid image.", index, rel_id)
                            continue
                        if rel.get("TargetMode", "").lower() == "external":
                            _warning(warnings, "external_image_reference", "External image was not downloaded or counted as a valid embedded image.", index, rel_id)
                            continue
                        if rel.get("Type") and not rel["Type"].rstrip("/").endswith("/image"):
                            _warning(warnings, "non_image_relationship", "Image element points to a non-image relationship; it was skipped.", index, rel_id)
                            continue
                        target, problem = _resolve_target(rel.get("Target", ""))
                        if problem:
                            _warning(warnings, problem, "Image target is external, empty, or unsafe; no target was read or extracted.", index, rel_id)
                            continue
                        if target not in members or zf.getinfo(target).is_dir():
                            _warning(warnings, "missing_image_part", "Referenced image part is absent from the archive; it was not counted as valid.", index, rel_id)
                            continue
                        if target not in members_cache:
                            data = _read_member(zf, target)
                            digest = hashlib.sha256(data).hexdigest()
                            width, height, suffix = image_dimensions(data)
                            if suffix is None:
                                original_suffix = Path(target).suffix.lower()
                                suffix = original_suffix if re.fullmatch(r"\.[a-z0-9]{1,8}", original_suffix) else ".bin"
                            relative_path = "media/" + digest + suffix
                            if digest not in payloads:
                                payloads[digest] = (relative_path, data)
                            else:
                                relative_path = payloads[digest][0]
                            members_cache[target] = (digest, relative_path, width, height)
                        digest, relative_path, width, height = members_cache[target]
                        if width is None or height is None:
                            _warning(warnings, "unknown_image_dimensions", "Image bytes were extracted, but dimensions could not be determined by the built-in header reader.", index, rel_id)
                        images.append({
                            "order": len(images) + 1,
                            "paragraph_index": index,
                            "relative_path": relative_path,
                            "sha256": digest,
                            "width": width,
                            "height": height,
                            "caption": _caption_candidate(index, texts),
                            "preceding_text": [t for t in texts[:index] if t][-CONTEXT_COUNT:],
                            "following_text": [t for t in texts[index + 1:] if t][:CONTEXT_COUNT],
                        })
    except (BadZipFile, RuntimeError, OSError) as exc:
        raise InventoryError("Could not read the DOCX archive: " + str(exc)) from exc
    if any(image["caption"] for image in images):
        _warning(warnings, "caption_candidates_unverified", "Caption values are nearby-text candidates only; confirm each unique anchor and placement against the source article.")
    manifest = {
        "schema_version": 1,
        "source": {"filename": source.name, "sha256": source_hash},
        "image_occurrences": len(images),
        "unique_media": len(payloads),
        "images": images,
        "warnings": warnings,
    }
    # Validate again immediately before writing. Never overwrite existing files.
    _check_output_directory(out)
    out.mkdir(parents=True, exist_ok=True)
    media_dir = out / "media"
    media_dir.mkdir(exist_ok=False)
    for relative_path, data in payloads.values():
        destination = out / relative_path
        if destination.parent != media_dir:
            raise InventoryError("Internal extraction path validation failed.")
        with destination.open("xb") as stream:
            stream.write(data)
    with (out / "manifest.json").open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path, help="Source .docx file (read only)")
    parser.add_argument("--out", required=True, type=Path, help="New or existing empty output directory")
    args = parser.parse_args(argv)
    try:
        manifest = build_inventory(args.source, args.out)
    except (InventoryError, OSError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        "manifest": str(args.out / "manifest.json"),
        "image_occurrences": manifest["image_occurrences"],
        "unique_media": manifest["unique_media"],
        "warnings": len(manifest["warnings"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
