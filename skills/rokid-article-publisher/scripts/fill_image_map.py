#!/usr/bin/env python3
"""Validate and fill image-upload placeholders without rewriting article text.

Purely local: no browser, network, login, upload, save, or publication actions.
The HTML fragment must already contain one top-level <img src="{{IMAGE_1}}">
per manifest occurrence. Existing native-hosted images may remain unchanged.
This validates mapping structure and origins, not the identity of online bytes.
"""

from __future__ import annotations

import argparse
import hashlib
from html import escape, unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


TOKEN = re.compile(r"\{\{IMAGE_(\d+)\}\}")
VOID = set("area base br col embed hr img input link meta param source track wbr".split())


class MappingError(ValueError):
    pass


def attribute_value_spans(raw):
    """Locate actual attributes while skipping quoted contents of other attributes."""
    opening = re.match(r"<\s*[A-Za-z][^\s/>]*", raw)
    if opening is None:
        raise MappingError("Invalid image start tag.")
    position = opening.end()
    result = []
    while position < len(raw):
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position >= len(raw) or raw[position] == ">" or raw.startswith("/>", position):
            break
        name_start = position
        while position < len(raw) and not raw[position].isspace() and raw[position] not in "=/>" :
            position += 1
        if name_start == position:
            raise MappingError("Cannot safely parse the image attributes.")
        name = raw[name_start:position].lower()
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position >= len(raw) or raw[position] != "=":
            result.append((name, None, None))
            continue
        position += 1
        while position < len(raw) and raw[position].isspace():
            position += 1
        if position >= len(raw):
            raise MappingError("Missing image attribute value.")
        quote = raw[position] if raw[position] in "\"'" else None
        if quote is not None:
            start = position + 1
            end = raw.find(quote, start)
            if end < 0:
                raise MappingError("Unclosed image attribute quote.")
            position = end + 1
        else:
            start = position
            while position < len(raw) and not raw[position].isspace() and raw[position] != ">":
                position += 1
            end = position
        result.append((name, start, end))
    return result


def origin_of(url):
    if not isinstance(url, str) or re.search(r"[\s\x00-\x1f\x7f]", url):
        raise MappingError("Image URLs must be nonempty HTTPS URLs without whitespace.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise MappingError("Invalid image URL.") from exc
    if parsed.scheme.lower() != "https" or not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise MappingError("Only HTTPS image URLs without embedded credentials are supported.")
    host = parsed.hostname.lower()
    if ":" in host:
        host = "[" + host + "]"
    return "https://" + host + (":" + str(port) if port not in (None, 443) else "")


def allowed_origin_set(origins):
    result = set()
    for url in origins:
        origin = origin_of(url)
        parsed = urlsplit(url)
        if parsed.path not in ("", "/") or parsed.query or parsed.fragment:
            raise MappingError("Allowed origins must contain scheme and host only.")
        result.add(origin)
    if not result:
        raise MappingError("Provide the origin observed after a native forum upload.")
    return result


class ImageScanner(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.source = source
        self.starts = [0] + [match.end() for match in re.finditer("\n", source)]
        self.stack = []
        self.images = []

    def _start(self, tag, attrs, closed):
        raw = self.get_starttag_text()
        line, col = self.getpos()
        offset = self.starts[line - 1] + col
        if tag == "img":
            srcs = [value for key, value in attrs if key == "src"]
            if len(srcs) != 1 or srcs[0] is None:
                raise MappingError("Every image must have exactly one src attribute.")
            if any(key == "srcset" for key, _ in attrs):
                raise MappingError("srcset needs explicit review; use a single verified native image src.")
            spans = [(start, end) for name, start, end in attribute_value_spans(raw) if name == "src"]
            if len(spans) != 1 or spans[0][0] is None:
                raise MappingError("Could not locate the original image src value.")
            start, end = spans[0]
            if unescape(raw[start:end]) != srcs[0]:
                raise MappingError("Parsed image src and original attribute value disagree.")
            self.images.append({
                "src": srcs[0],
                "start": offset + start,
                "end": offset + end,
                "ancestors": tuple(self.stack),
            })
        if not closed and tag not in VOID:
            self.stack.append(tag)

    def handle_starttag(self, tag, attrs):
        self._start(tag, attrs, False)

    def handle_startendtag(self, tag, attrs):
        self._start(tag, attrs, True)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if tag not in self.stack:
            raise MappingError("Unbalanced HTML end tag; review the article fragment first.")
        if self.stack[-1] != tag:
            raise MappingError("Misnested HTML; review the article fragment first.")
        self.stack.pop()


def scan_images(source):
    scanner = ImageScanner(source)
    try:
        scanner.feed(source)
        scanner.close()
    except MappingError:
        raise
    except Exception as exc:
        raise MappingError("Could not parse the article HTML.") from exc
    if scanner.stack:
        raise MappingError("Unclosed HTML tags; review the article fragment first.")
    return scanner.images


def checked_rows(document, label):
    rows = document.get("images") if isinstance(document, dict) else None
    if not isinstance(rows, list):
        raise MappingError(label + " must contain an images array.")
    result = {}
    for row in rows:
        if not isinstance(row, dict):
            raise MappingError(label + " image records must be objects.")
        order = row.get("order")
        if type(order) is not int or order < 1 or order in result:
            raise MappingError(label + " orders must be distinct positive integers.")
        result[order] = row
    if set(result) != set(range(1, len(rows) + 1)):
        raise MappingError(label + " orders must be contiguous, starting at 1.")
    return dict(sorted(result.items()))


def fill_image_map(template, manifest, uploads, allowed_origins):
    """Return (HTML, audit). Only placeholder src byte ranges are replaced."""
    allowed = allowed_origin_set(allowed_origins)
    expected = checked_rows(manifest, "Manifest")
    mapping = checked_rows(uploads, "Upload mapping")
    if manifest.get("image_occurrences", len(expected)) != len(expected):
        raise MappingError("Manifest image_occurrences does not agree with its images array.")
    if set(mapping) != set(expected):
        raise MappingError("Upload mapping must cover exactly the manifest occurrences.")
    urls = {}
    for order, row in mapping.items():
        url = row.get("url")
        if origin_of(url) not in allowed:
            raise MappingError("Image " + str(order) + " is not on an allowed native-upload origin.")
        urls[order] = url
    seen = set()
    replacements = []
    expected_output_sources = []
    existing = 0
    for image in scan_images(template):
        if any(tag not in ("html", "body") for tag in image["ancestors"]):
            raise MappingError("Images must be top-level in the pasted body fragment.")
        match = TOKEN.fullmatch(image["src"])
        if match is None:
            if origin_of(image["src"]) not in allowed:
                raise MappingError("An existing image uses an unverified external origin or temporary src.")
            existing += 1
            expected_output_sources.append(image["src"])
            continue
        order = int(match.group(1))
        if order not in expected or order in seen:
            raise MappingError("Each manifest image needs one unique placeholder src.")
        seen.add(order)
        expected_output_sources.append(urls[order])
        replacements.append((image["start"], image["end"], escape(urls[order], quote=True), order))
    if seen != set(expected):
        raise MappingError("Missing image placeholders; no output was written.")
    raw_tokens = list(TOKEN.finditer(template))
    if len(raw_tokens) != len(replacements):
        raise MappingError("Reserved image tokens appear outside their intended src attributes.")
    # Preserve the author's image order; do not silently rearrange the template.
    if [r[3] for r in replacements] != list(expected):
        raise MappingError("Placeholder order differs from manifest order; confirm placement first.")
    pieces = []
    preserved = []
    position = 0
    for start, end, replacement, _ in replacements:
        pieces.extend((template[position:start], replacement))
        preserved.append(template[position:start])
        position = end
    pieces.append(template[position:])
    preserved.append(template[position:])
    output = "".join(pieces)
    verified = scan_images(output)
    if len(verified) != len(expected) + existing:
        raise MappingError("Final image count changed unexpectedly.")
    if [image["src"] for image in verified] != expected_output_sources:
        raise MappingError("Final image src values do not match the upload mapping.")
    if TOKEN.search(output):
        raise MappingError("An image placeholder remains in the final HTML.")
    audit = {
        "schema_version": 1,
        "image_occurrences": len(expected),
        "existing_images_preserved": existing,
        "only_placeholder_src_values_changed": True,
        "non_src_content_sha256": hashlib.sha256("".join(preserved).encode("utf-8")).hexdigest(),
        "targets": [{"order": order, "origin": origin_of(urls[order])} for order in expected],
        "limitations": ["URL mapping identity, loading, image placement, and persistence still require verification in the live editor and refreshed post."],
    }
    return output, audit


def new_output_directory(path):
    if path.is_symlink() or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
        raise MappingError("Output must be a new or existing empty directory, not a symlink.")
    path.mkdir(parents=True, exist_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--uploads", type=Path, required=True)
    parser.add_argument("--allowed-origin", action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        template = args.template.read_text(encoding="utf-8")
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        uploads = json.loads(args.uploads.read_text(encoding="utf-8"))
        output, audit = fill_image_map(template, manifest, uploads, args.allowed_origin)
        new_output_directory(args.out)
        with (args.out / "article.html").open("x", encoding="utf-8") as stream:
            stream.write(output)
        with (args.out / "audit.json").open("x", encoding="utf-8") as stream:
            json.dump(audit, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 2
    print(json.dumps({"image_occurrences": audit["image_occurrences"], "existing_images_preserved": audit["existing_images_preserved"], "html": str(args.out / "article.html")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
