#!/usr/bin/env python3
"""Offline, conservative TXT/Markdown preparation; never uploads or executes prose."""
from __future__ import annotations

import argparse
import codecs
import hashlib
import html
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

SCHEMA_VERSION = 1
IMAGE_TOKEN = re.compile(r"\{\{CS_IMAGE_\d{4,}\}\}")
ESCAPABLE = re.compile(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])")


class PreparationError(ValueError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def escaped(text: str, pos: int) -> bool:
    start = pos
    while start > 0 and text[start - 1] == "\\":
        start -= 1
    return (pos - start) % 2 == 1


def decode_text(raw: bytes, encoding: str | None) -> tuple[str, str]:
    if encoding:
        used = codecs.lookup(encoding).name
    elif raw.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
        raise PreparationError("UTF-32 is not auto-detected; specify --encoding utf-32 explicitly.")
    elif raw.startswith(codecs.BOM_UTF8):
        used = "utf-8-sig"
    elif raw.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        used = "utf-16"
    else:
        used = "utf-8"
    try:
        text = raw.decode(used)
    except (UnicodeError, LookupError) as exc:
        raise PreparationError("Cannot decode source. For GB18030, use --encoding gb18030.") from exc
    if "\x00" in text:
        raise PreparationError("Decoded source contains NUL bytes; check the encoding or file type.")
    return text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n"), used


def literal_markdown(text: str) -> str:
    """Escape TXT as prose; hard breaks retain nonempty source line boundaries."""
    lines = []
    for line in text.split("\n"):
        line = html.escape(line, quote=False)
        line = re.sub(r"([\\`*_{}\[\]()#+\-.!|~])", r"\\\1", line)
        # Entity-based indentation avoids accidentally creating indented code blocks.
        leading = len(line) - len(line.lstrip(" \t"))
        indent = line[:leading].replace(" ", "&#32;").replace("\t", "&#9;")
        line = indent + line[leading:]
        lines.append(line + ("  " if line else ""))
    return "\n".join(lines)


def code_mask(text: str) -> tuple[list[bool], list[str], list[str]]:
    """Mask ordinary fenced/indented/inline code. Fail closed on list-indent ambiguity."""
    mask = [False] * len(text)
    blocks, warnings = [], []
    offset = 0
    fence = None
    current = []
    indented = []
    in_list = False
    paragraph_open = False
    for line in text.splitlines(keepends=True):
        stripped = line.rstrip("\n")
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", stripped)
        if not fence and re.match(r"^ {0,3}(?:>\s*|[-+*]\s+|\d+[.)]\s+)(?:`{3,}|~{3,})", stripped):
            warnings.append("container_code_fence_requires_normalization: move quoted or list-prefixed code fences to a plain fenced block")
        is_indented = bool(re.match(r"^(?: {4}|\t)", line))
        is_list = bool(re.match(r"^ {0,3}(?:[-+*]|\d{1,9}[.)])\s", line))
        if is_list:
            in_list = True
        elif stripped.strip() and not is_indented and not fence:
            in_list = False
        coded = False
        if fence:
            coded = True
            current.append(line)
            closing = re.match(r"^ {0,3}(" + re.escape(fence[0]) + r"{" + str(fence[1]) + r",})\s*$", stripped)
            if closing:
                blocks.append("".join(current))
                fence = None
                current = []
        elif opening and not (opening[1][0] == "`" and "`" in opening[2]):
            if indented:
                blocks.append("".join(indented))
                indented = []
            fence = (opening[1][0], len(opening[1]))
            coded = True
            current = [line]
        elif is_indented:
            # Four spaces cannot interrupt an already open ordinary paragraph.
            if in_list or not paragraph_open:
                coded = True
                indented.append(line)
                if in_list and ("![" in line or re.search(r"<\s*img\b", line, re.I)):
                    warnings.append("ambiguous_indented_image: image-like syntax inside an indented list needs manual normalization")
        elif indented:
            blocks.append("".join(indented))
            indented = []
        if coded:
            mask[offset:offset + len(line)] = [True] * len(line)
        if coded or not stripped.strip() or re.match(r"^ {0,3}(?:#{1,6}(?:\s|$)|(?:[-*_]\s*){3,}$)", stripped):
            paragraph_open = False
        else:
            paragraph_open = True
        offset += len(line)
    if current:
        blocks.append("".join(current))
    if indented:
        blocks.append("".join(indented))
    # Comments must be masked before inline backticks: punctuation inside a comment
    # cannot open a code span which consumes visible text following the comment.
    comment_start = 0
    while True:
        comment_start = text.find("<!--", comment_start)
        if comment_start < 0:
            break
        if mask[comment_start] or escaped(text, comment_start):
            comment_start += 4
            continue
        # If a comment opener might lie inside an inline code span, do not guess
        # precedence. A false comment match must never silently hide a real image.
        paragraph_breaks = list(re.finditer(r"\n[ \t]*\n", text[:comment_start]))
        paragraph_start = paragraph_breaks[-1].end() if paragraph_breaks else 0
        pending_run = None
        for delimiter in re.finditer(r"`+", text[paragraph_start:comment_start]):
            absolute = paragraph_start + delimiter.start()
            if mask[absolute] or escaped(text, absolute):
                continue
            length = len(delimiter[0])
            if pending_run is None:
                pending_run = length
            elif pending_run == length:
                pending_run = None
        if pending_run is not None:
            warnings.append("comment_code_interaction_requires_review: normalize interleaved inline-code and HTML-comment delimiters before publishing")
        comment_end = text.find("-->", comment_start + 4)
        if comment_end < 0:
            warnings.append("unclosed_html_comment_requires_review: close the comment before publishing")
            mask[comment_start:] = [True] * (len(text) - comment_start)
            break
        comment_end += 3
        mask[comment_start:comment_end] = [True] * (comment_end - comment_start)
        comment_start = comment_end
    # Inline backtick delimiters must match the entire run length.
    pos = 0
    while pos < len(text):
        if mask[pos] or text[pos] != "`" or escaped(text, pos):
            pos += 1
            continue
        end = pos
        while end < len(text) and text[end] == "`" and not mask[end]:
            end += 1
        run = end - pos
        close = end
        found = None
        block_break = re.search(r"\n[ \t]*\n|\n {0,3}(?:#{1,6}(?:\s|$)|>|[-+*]\s|\d{1,9}[.)]\s)", text[end:])
        limit = end + block_break.start() + 1 if block_break else len(text)
        while close < limit:
            if mask[close]:
                break
            if text[close] != "`":
                close += 1
                continue
            right = close
            while right < len(text) and text[right] == "`" and not mask[right]:
                right += 1
            if right - close == run:
                found = right
                break
            close = right
        if found is not None:
            mask[pos:found] = [True] * (found - pos)
            pos = found
        else:
            pos = end
    return mask, blocks, warnings


def bracket_end(text: str, start: int, left: str = "[", right: str = "]") -> int | None:
    depth = 1
    pos = start + 1
    while pos < len(text):
        if escaped(text, pos):
            pos += 1
            continue
        if text[pos] == left:
            depth += 1
        elif text[pos] == right:
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    return None


def parse_destination(text: str, start: int) -> tuple[str, int] | None:
    pos = start
    while pos < len(text) and text[pos].isspace():
        pos += 1
    begin = pos
    if pos < len(text) and text[pos] == "<":
        pos += 1
        begin = pos
        while pos < len(text):
            if text[pos] == "\n" or (text[pos] == "<" and not escaped(text, pos)):
                return None
            if text[pos] == ">" and not escaped(text, pos):
                return text[begin:pos], pos + 1
            pos += 1
        return None
    depth = 0
    while pos < len(text):
        char = text[pos]
        if not escaped(text, pos):
            if char.isspace():
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    break
                depth -= 1
        pos += 1
    if depth != 0:
        return None
    return text[begin:pos], pos


def consume_title(text: str, pos: int) -> int | None:
    if pos >= len(text) or text[pos] not in "\"'(":
        return None
    closing = ")" if text[pos] == "(" else text[pos]
    pos += 1
    while pos < len(text):
        if text[pos] == closing and not escaped(text, pos):
            return pos + 1
        pos += 1
    return None


def norm_label(label: str) -> str:
    # CommonMark labels normalize whitespace/case, not entities or backslash escapes.
    return " ".join(label.split()).casefold()


def decode_destination(value: str) -> str:
    return html.unescape(ESCAPABLE.sub(r"\1", value))


def reference_definitions(text: str, mask: list[bool]) -> dict[str, dict]:
    refs = {}
    offset = 0
    lines = text.splitlines(keepends=True)
    can_define = True
    consumed_titles = set()
    for line_index, line in enumerate(lines):
        accepted = False
        match = re.match(r"^ {0,3}\[([^\n]+)\]:[ \t]*(.*)$", line.rstrip("\n"))
        if can_define and match and not any(mask[offset:offset + len(line)]):
            parsed = parse_destination(match[2], 0)
            if parsed:
                dest, end = parsed
                rest = match[2][end:].strip()
                if not rest and line_index + 1 < len(lines):
                    next_line = lines[line_index + 1]
                    next_start = offset + len(line)
                    candidate_title = next_line.strip()
                    if (candidate_title and not any(mask[next_start:next_start + len(next_line)])
                            and consume_title(candidate_title, 0) == len(candidate_title)):
                        rest = candidate_title
                        consumed_titles.add(line_index + 1)
                if not rest or consume_title(rest, 0) == len(rest):
                    refs.setdefault(norm_label(match[1]), {"destination": dest, "title": rest})
                    accepted = True
        can_define = bool(
            accepted or line_index in consumed_titles or not line.strip()
            or (line and all(mask[offset:offset + len(line)]))
            or re.match(r"^ {0,3}(?:#{1,6}(?:\s|$)|(?:[-*_]\s*){3,}$)", line.rstrip("\n"))
        )
        offset += len(line)
    return refs


def scan_images(text: str, mask: list[bool], refs: dict[str, dict]) -> tuple[list[dict], list[str]]:
    images, problems = [], []
    pos = 0
    while pos < len(text) - 1:
        if mask[pos] or text[pos:pos + 2] != "![" or escaped(text, pos):
            pos += 1
            continue
        close = bracket_end(text, pos + 1)
        if close is None or any(mask[pos:close + 1]):
            problems.append("unsupported_image_syntax: unbalanced or code-containing image label")
            pos += 2
            continue
        alt = text[pos + 2:close]
        end = close + 1
        dest = None
        title = ""
        if end < len(text) and text[end] == "(":
            parsed = parse_destination(text, end + 1)
            if parsed:
                dest, tail = parsed
                separated = tail < len(text) and text[tail].isspace()
                while tail < len(text) and text[tail].isspace():
                    tail += 1
                if tail < len(text) and text[tail] != ")" and separated:
                    title_start = tail
                    tail = consume_title(text, tail)
                    if tail is not None:
                        title = text[title_start:tail]
                        while tail < len(text) and text[tail].isspace():
                            tail += 1
                if tail is not None and tail < len(text) and text[tail] == ")":
                    end = tail + 1
                else:
                    dest = None
        elif end < len(text) and text[end] == "[":
            ref_end = bracket_end(text, end)
            if ref_end is not None:
                label = text[end + 1:ref_end] or alt
                reference = refs.get(norm_label(label))
                if reference:
                    dest, title = reference["destination"], reference["title"]
                end = ref_end + 1
        else:
            reference = refs.get(norm_label(alt))
            if reference:
                dest, title = reference["destination"], reference["title"]
        if dest is None:
            problems.append("unresolved_image_syntax: image reference is undefined or outside the supported syntax")
            pos = close + 1
            continue
        images.append({"start": pos, "end": end, "alt": alt, "source": decode_destination(dest), "title": title})
        pos = end
    return images, problems


def image_extension(raw: bytes) -> str | None:
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if raw.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if raw.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return ".webp"
    return None


def classify_image(source_dir: Path, value: str) -> tuple[str, Path | None, str | None]:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return "blocked", None, "invalid_image_url"
    if parsed.scheme.lower() in ("http", "https") or value.startswith("//"):
        return "remote", None, "remote_image_requires_local_authorized_copy"
    if parsed.scheme or parsed.netloc:
        return "blocked", None, "unsupported_image_scheme"
    local = unquote(parsed.path)
    if not local or "\x00" in local or "\\" in local:
        return "blocked", None, "invalid_local_image_path"
    relative = Path(local)
    if relative.is_absolute() or re.match(r"^[A-Za-z]:", local):
        return "blocked", None, "absolute_image_path_not_allowed"
    try:
        resolved = (source_dir / relative).resolve()
    except (OSError, RuntimeError):
        return "blocked", None, "image_path_cannot_be_resolved_safely"
    try:
        resolved.relative_to(source_dir)
    except ValueError:
        return "blocked", None, "image_path_outside_source_directory"
    if not resolved.is_file():
        return "missing", None, "local_image_missing"
    return "local", resolved, None


def structural_baseline(text: str) -> dict:
    mask, code, _ = code_mask(text)
    headings, lists = [], []
    offset = 0
    prev_line = None
    for line in text.splitlines(keepends=True):
        first_content = len(line) - len(line.lstrip(" \t"))
        visible = offset + first_content < len(mask) and not mask[offset + first_content]
        clean = line.rstrip("\n")
        if visible:
            if re.match(r"^ {0,3}#{1,6}(?:\s|$)", clean):
                headings.append(clean)
            elif prev_line and re.match(r"^ {0,3}(?:=+|-+)\s*$", clean):
                headings.append(prev_line + "\n" + clean)
            if re.match(r"^ {0,3}(?:[-+*]|\d{1,9}[.)])\s", clean):
                lists.append(clean)
        prev_line = clean if visible and clean.strip() else None
        offset += len(line)
    return {
        "heading_count": len(headings), "code_block_count": len(code),
        "list_item_count": len(lists),
        "headings_sha256": digest("\n".join(headings).encode()),
        "code_blocks_sha256": [digest(block.encode()) for block in code],
        "list_items_sha256": digest("\n".join(lists).encode()),
        "counting_mode": "conservative_markdown_scan_not_full_commonmark",
    }


def validate_output(path: Path) -> None:
    if path.is_symlink():
        raise PreparationError("Output directory cannot be a symbolic link.")
    for parent in path.parents:
        if parent.is_symlink():
            raise PreparationError("Output parent path cannot contain symbolic links; use its real path.")
    if path.exists() and (not path.is_dir() or any(path.iterdir())):
        raise PreparationError("Output must be a new or empty directory; existing files are never overwritten.")


def prepare(source: Path, output: Path, encoding: str | None = None, txt_as_markdown: bool = False) -> dict:
    source = source.absolute()
    output = output.absolute()
    validate_output(output)
    if source.is_symlink() or not source.is_file():
        raise PreparationError("Source must be a regular file, not a symbolic link.")
    suffix = source.suffix.lower()
    if suffix not in (".txt", ".md", ".markdown"):
        raise PreparationError("Supported source extensions: .txt, .md, .markdown.")
    if txt_as_markdown and suffix != ".txt":
        raise PreparationError("--txt-as-markdown applies only to .txt sources.")
    raw = source.read_bytes()
    text, used_encoding = decode_text(raw, encoding)
    if IMAGE_TOKEN.search(text):
        raise PreparationError("Source already contains reserved {{CS_IMAGE_...}} placeholders; use an original source.")
    markdown_mode = suffix != ".txt" or txt_as_markdown
    article = text if markdown_mode else literal_markdown(text)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "source": {"filename": source.name, "sha256": digest(raw), "format": suffix[1:]},
        "input_encoding": used_encoding,
        "input_mode": "markdown" if markdown_mode else "literal_text",
        "title_suggestion": source.stem,
        "images": [], "warnings": [], "blocking_issues": [],
    }
    image_bytes = {}
    if markdown_mode:
        mask, _, ambiguity = code_mask(text)
        manifest["blocking_issues"].extend(ambiguity)
        if re.match(r"^(?:---|\+\+\+)\s*\n", text):
            manifest["blocking_issues"].append("frontmatter_requires_review: separate YAML/TOML frontmatter from article prose in an approved source copy")
        visible = "".join(" " if masked else char for char, masked in zip(text, mask))
        refs = reference_definitions(text, mask)
        occurrences, problems = scan_images(text, mask, refs)
        html_visible = list(visible)
        for item in occurrences:
            html_visible[item["start"]:item["end"]] = " " * (item["end"] - item["start"])
        for definition in re.finditer(r"(?m)^ {0,3}\[([^\n]+)\]:[^\n]*", text):
            if norm_label(definition[1]) in refs:
                html_visible[definition.start():definition.end()] = " " * (definition.end() - definition.start())
        html_visible = "".join(html_visible)
        if re.search(r"<\s*img\b", html_visible, re.I):
            manifest["blocking_issues"].append("html_img_requires_conversion: change HTML img tags into standard Markdown image references")
        if re.search(r"<\s*(?:script|iframe|object|embed|style)\b", html_visible, re.I):
            manifest["blocking_issues"].append("active_html_requires_manual_review: raw active HTML is not a supported publishing input")
        if re.search(r"<\s*/?[A-Za-z][A-Za-z0-9:-]*(?=[\s/>])", html_visible):
            manifest["blocking_issues"].append("raw_html_requires_review: normalize HTML tags to supported Markdown before publishing")
        # Container-prefixed fences are intentionally not interpreted as CommonMark.
        if re.search(r"(?m)^ {0,3}(?:>\s*|[-+*]\s+|\d+[.)]\s+)(?:`{3,}|~{3,})", visible):
            manifest["blocking_issues"].append("container_code_fence_requires_normalization: move quoted or list-prefixed code fences to a plain fenced block")
        manifest["blocking_issues"].extend(problems)
        for order, item in enumerate(occurrences, 1):
            token = "{{CS_IMAGE_%04d}}" % order
            kind, path, problem = classify_image(source.parent.resolve(), item["source"])
            entry = {
                "order": order, "placeholder": token, "original_source": item["source"],
                "kind": kind, "relative_path": None, "sha256": None, "alt": item["alt"],
            }
            if path:
                data = path.read_bytes()
                extension = image_extension(data)
                if extension is None:
                    entry["kind"] = "blocked"
                    problem = "unsupported_image_format: use PNG, JPEG, GIF or WebP; SVG and unknown formats require manual conversion"
                else:
                    checksum = digest(data)
                    filename = "media/" + checksum + extension
                    entry.update(relative_path=filename, sha256=checksum)
                    image_bytes.setdefault(filename, data)
            if problem:
                manifest["blocking_issues"].append(token + ": " + problem)
            manifest["images"].append(entry)
        for item, entry in reversed(list(zip(occurrences, manifest["images"]))):
            replacement = "![" + item["alt"] + "](" + entry["placeholder"] + (" " + item["title"] if item["title"] else "") + ")"
            article = article[:item["start"]] + replacement + article[item["end"]:]
        match = re.search(r"(?m)^ {0,3}#{1,6}[ \t]+(.+?)\s*#*\s*$", visible)
        if match:
            manifest["title_suggestion"] = match[1][:120]
        manifest["warnings"].append("Markdown is preserved, not fully rendered. Structural counts use a conservative scanner; review the CSDN preview.")
    else:
        first = next((line.strip() for line in text.splitlines() if line.strip()), "")
        if first:
            manifest["title_suggestion"] = first[:120]
        manifest["warnings"].append("TXT is literal prose. Image-looking text is not uploaded; opt into --txt-as-markdown only for intentionally authored Markdown.")
    manifest["baseline"] = structural_baseline(text if markdown_mode else article)
    manifest["baseline"].update(
        source_text_sha256=digest(text.encode()),
        prepared_markdown_sha256=digest(article.encode()),
        image_occurrence_count=len(manifest["images"]),
        local_unique_image_count=len(image_bytes),
    )
    manifest["blocking_issues"] = list(dict.fromkeys(manifest["blocking_issues"]))
    manifest["ready_for_upload"] = not manifest["blocking_issues"]
    # Recheck just before writes. 'x' below independently refuses existing files.
    validate_output(output)
    output.mkdir(parents=True, exist_ok=True)
    if image_bytes:
        (output / "media").mkdir()
    for name, data in image_bytes.items():
        with (output / name).open("xb") as handle:
            handle.write(data)
    with (output / "article.md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(article)
    with (output / "manifest.json").open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--encoding", help="Explicit input encoding, e.g. gb18030. Default: UTF-8 or BOM-marked UTF-16.")
    parser.add_argument("--txt-as-markdown", action="store_true", help="Explicitly parse a .txt file as Markdown instead of literal prose.")
    args = parser.parse_args()
    try:
        result = prepare(args.source, args.output, args.encoding, args.txt_as_markdown)
    except (PreparationError, OSError, LookupError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"output": str(args.output.absolute()), "image_occurrences": len(result["images"]), "blocking_issues": result["blocking_issues"], "ready_for_upload": result["ready_for_upload"]}, ensure_ascii=False, indent=2))
    return 0 if result["ready_for_upload"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
