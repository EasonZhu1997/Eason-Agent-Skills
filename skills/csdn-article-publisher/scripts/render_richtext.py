#!/usr/bin/env python3
"""Render finalized Markdown into safe semantic HTML for a reviewed UI transfer."""

import argparse
import codecs
import hashlib
import html
import json
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

try:
    from markdown_it import MarkdownIt
except ImportError:
    MarkdownIt = None


PLACEHOLDER = re.compile(r"\{\{(?:CS|RK|ZH|JJ)_IMAGE_", re.IGNORECASE)
HOST = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")


class ValidationError(Exception):
    """Diagnostics intentionally exclude body contents and signed URLs."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def json_digest(value):
    return digest(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def validate_link(url):
    """Called by the parser before making a link or image token."""
    if not isinstance(url, str) or not url or any(ord(c) < 32 or ord(c) == 127 for c in url):
        raise ValidationError("A link target is empty or contains control characters")
    if url.startswith("#"):
        return True
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        port = parts.port
    except ValueError:
        raise ValidationError("A link target cannot be parsed safely") from None
    if parts.scheme in ("http", "https"):
        if not hostname or not parts.netloc or parts.username is not None or parts.password is not None:
            raise ValidationError("Web links require a hostname and must not contain credentials")
        if port is not None and not 1 <= port <= 65535:
            raise ValidationError("A web link has an invalid port")
        return True
    if parts.scheme == "mailto" and parts.path and not parts.netloc:
        return True
    raise ValidationError("Links must use HTTP, HTTPS, mailto, or a same-page anchor; normalize other links first")


def validate_extra_hosts(hosts):
    result = set()
    for host in hosts:
        if not isinstance(host, str) or not HOST.fullmatch(host) or host != host.lower():
            raise ValidationError("--allow-host requires one exact lowercase hostname, without scheme, path, wildcard or port")
        result.add(host)
    return result


def validate_image(url, extra_hosts=()):
    validate_link(url)
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        raise ValidationError("An image URL cannot be parsed safely") from None
    if parts.scheme != "https" or port not in (None, 443):
        raise ValidationError("Images require HTTPS and the default HTTPS port")
    if not HOST.fullmatch(host) or not (host in ("i-blog.csdnimg.cn", "img-blog.csdnimg.cn") or host in extra_hosts):
        raise ValidationError("Images must use a native-upload CSDN image host or an explicitly verified exact --allow-host")
    if not parts.path or parts.path == "/":
        raise ValidationError("An image URL must identify an image resource")


def inline_text(tokens):
    result = []
    for token in tokens or []:
        if token.type in ("text", "code_inline"):
            result.append(token.content)
        elif token.type in ("softbreak", "hardbreak"):
            result.append("\n")
        elif token.type == "image":
            result.append(inline_text(token.children) or token.content)
    return "".join(result)


def reject_html_comments(source):
    # Parse only, never render. With HTML disabled, hidden editorial comments would
    # otherwise become visible text. CommonMark tokens distinguish code examples.
    detector = MarkdownIt("commonmark", {"html": True})
    tokens = detector.parse(source)

    def inspect(items):
        for token in items:
            if token.type in ("html_inline", "html_block") and "<!--" in token.content:
                raise ValidationError("HTML comments may contain private editorial notes; review and remove or rewrite them in a working copy before rendering")
            if token.children:
                inspect(token.children)

    inspect(tokens)


def render_document(source_bytes, extra_hosts=()):
    if MarkdownIt is None:
        raise ValidationError("Missing markdown-it-py; install requirements-render.txt in a suitable virtual environment")
    try:
        source = source_bytes.decode("utf-8")
    except (UnicodeError, AttributeError):
        raise ValidationError("Input must be finalized UTF-8 Markdown") from None
    if "\x00" in source:
        raise ValidationError("Input contains a NUL character")
    if PLACEHOLDER.search(source):
        raise ValidationError("Unresolved image placeholders remain; finalize images before rendering")
    extra_hosts = validate_extra_hosts(extra_hosts)
    reject_html_comments(source)
    # No raw HTML, automatic URLs, typography changes, external plugins, or code execution.
    md = MarkdownIt("commonmark", {"html": False, "linkify": False, "typographer": False})
    md.enable(["table", "strikethrough"])
    # Parse candidate targets without side effects. Definitions left unused after
    # image finalization may retain local paths, so validate actual output tokens
    # below, before invoking the renderer, instead of rejecting definitions here.
    md.validateLink = lambda url: True
    tokens = md.parse(source)
    images, headings, codes, links, ordered_lists = [], [], [], [], []

    def inspect(items):
        for index, token in enumerate(items):
            if token.type == "image":
                src = token.attrGet("src") or ""
                validate_image(src, extra_hosts)
                images.append({"order": len(images) + 1, "url": src,
                               "alt": inline_text(token.children) or token.content,
                               "title": token.attrGet("title")})
            elif token.type == "heading_open":
                inline = items[index + 1] if index + 1 < len(items) else None
                headings.append({"level": int(token.tag[1:]),
                                 "text": inline_text(inline.children) if inline else ""})
            elif token.type in ("fence", "code_block", "code_inline"):
                codes.append({"kind": token.type, "info": token.info,
                              "content_sha256": digest(token.content.encode("utf-8")),
                              "content": token.content})
            elif token.type == "link_open":
                href = token.attrGet("href") or ""
                validate_link(href)
                links.append(href)
            elif token.type == "ordered_list_open":
                ordered_lists.append(int(token.attrGet("start") or 1))
            # Image children become plain alt text, not independent DOM images/code.
            if token.children and token.type != "image":
                inspect(token.children)

    inspect(tokens)
    fragment = md.renderer.render(tokens, md.options, {})
    preview = build_preview(fragment, extra_hosts)
    manifest = {
        "schema_version": 1,
        "state": "ready_for_reviewed_ui_transfer_not_published",
        "source_format": "markdown",
        "source_sha256": digest(source_bytes),
        "source_markdown_sha256": digest(source_bytes),
        "fragment_sha256": digest(fragment.encode("utf-8")),
        "preview_sha256": digest(preview.encode("utf-8")),
        "images": images,
        "headings": headings,
        "code": codes,
        "links": links,
        "ordered_list_starts": ordered_lists,
        "additional_allowed_image_hosts": sorted(extra_hosts),
        "baseline": {
            "image_count": len(images), "heading_count": len(headings),
            "code_count": len(codes), "headings_sha256": json_digest(headings),
            "code_sha256": json_digest(codes),
            "tables": sum(t.type == "table_open" for t in tokens),
        },
        "warnings": [
            "HTML clipboard support and the current CSDN editor must be inspected; this is not an upload API.",
            "The destination may transform formatting; verify rendered headings, code, tables, image order and links.",
            "Markdown code content follows CommonMark line-ending and terminal-newline semantics; no code is executed.",
        ],
    }
    return fragment, preview, manifest


def build_preview(fragment, extra_hosts=()):
    image_csp = "https://i-blog.csdnimg.cn https://img-blog.csdnimg.cn" + "".join(" https://" + host for host in sorted(extra_hosts))
    return """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src """ + image_csp + """; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<meta name="referrer" content="no-referrer">
<title>CSDN文章转入前预览</title>
<style>body{max-width:820px;margin:40px auto;padding:0 24px;font:18px/1.8 system-ui,sans-serif;color:#222}img{max-width:100%;height:auto}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:16px;background:#f5f5f5}code{font-family:monospace}table{border-collapse:collapse}td,th{border:1px solid #bbb;padding:6px 12px}blockquote{border-left:3px solid #bbb;margin-left:0;padding-left:18px}header{padding:12px;background:#eef4ff;font-size:14px}</style>
</head><body><header>离线生成的检查页；不是CSDN实际排版。复制文章区域，不复制本提示。打开本页时，浏览器可能请求已上传的CSDN图片；本页不包含脚本。</header>
<article id="article-to-copy">
""" + fragment + "</article>\n</body></html>\n"


def render_literal_text(source_bytes, encoding=None):
    """Use semantic preformatted text, not Markdown or whitespace-altering NBSP."""
    try:
        if encoding:
            used = codecs.lookup(encoding).name
        elif source_bytes.startswith((codecs.BOM_UTF32_LE, codecs.BOM_UTF32_BE)):
            raise ValidationError("UTF-32 is not auto-detected; specify --encoding utf-32 explicitly")
        elif source_bytes.startswith(codecs.BOM_UTF8):
            used = "utf-8-sig"
        elif source_bytes.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
            used = "utf-16"
        else:
            used = "utf-8"
        text = source_bytes.decode(used).lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    except (UnicodeError, LookupError, AttributeError):
        raise ValidationError("Cannot decode TXT input; confirm its encoding and use --encoding when needed") from None
    if "\x00" in text:
        raise ValidationError("TXT input contains NUL; check the encoding or source file")
    # HTML parsers consume exactly one immediate LF after a <pre> start tag.
    # Supply that structural LF explicitly, leaving every source LF untouched.
    fragment = '<pre style="font-family:inherit">\n' + html.escape(text, quote=False) + "</pre>\n"
    preview = build_preview(fragment)
    text_hash = digest(text.encode("utf-8"))
    manifest = {
        "schema_version": 1,
        "state": "ready_for_reviewed_ui_transfer_not_published",
        "source_format": "txt",
        "input_mode": "literal_preformatted_text",
        "input_encoding": used,
        "source_sha256": digest(source_bytes),
        "fragment_sha256": digest(fragment.encode("utf-8")),
        "preview_sha256": digest(preview.encode("utf-8")),
        "literal_text": text,
        "images": [], "headings": [], "code": [], "links": [],
        "ordered_list_starts": [], "additional_allowed_image_hosts": [],
        "baseline": {
            "image_count": 0, "heading_count": 0, "code_count": 0, "tables": 0,
            "literal_text_sha256": text_hash, "literal_character_count": len(text),
            "literal_linefeed_count": text.count("\n"),
        },
        "warnings": [
            "TXT is one semantic preformatted text block, not Markdown or a programming-language code block.",
            "BOM decoding and CRLF/CR-to-LF normalization precede the exact text baseline.",
            "The destination may transform preformatted text; verify spaces, tabs, blank lines and literal characters after transfer.",
        ],
    }
    return fragment, preview, manifest


def reject_symlink_path(path):
    path = Path(path).absolute()
    for component in (path,) + tuple(path.parents):
        if component.is_symlink():
            raise ValidationError("Input/output paths and existing ancestors must not be symbolic links")
    return path


def convert_file(source, output, extra_hosts=(), literal_txt=False, encoding=None):
    source = reject_symlink_path(source)
    output = reject_symlink_path(output)
    if not source.is_file():
        raise ValidationError("Input must be a regular file")
    try:
        if output.exists() and (not output.is_dir() or any(output.iterdir())):
            raise ValidationError("Output must be a new or empty directory")
        if literal_txt:
            if extra_hosts:
                raise ValidationError("Literal TXT has no uploaded images; omit --allow-host")
            fragment, preview, manifest = render_literal_text(source.read_bytes(), encoding)
        else:
            if encoding:
                raise ValidationError("--encoding is only for --literal-txt; finalized Markdown must be UTF-8")
            fragment, preview, manifest = render_document(source.read_bytes(), extra_hosts)
        output.mkdir(parents=True, exist_ok=True)
        contents = {
            "article.fragment.html": fragment,
            "preview.html": preview,
            "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        }
        for name, value in contents.items():
            with (output / name).open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(value)
    except ValidationError:
        raise
    except (OSError, UnicodeError):
        raise ValidationError("Cannot read the source or safely create new output files; no existing file was overwritten") from None
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument("--article", type=Path, help="Finalized UTF-8 Markdown")
    source_group.add_argument("--literal-txt", type=Path, help="Original plain TXT, preserving literal characters and whitespace")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--encoding", help="Explicit TXT encoding, for example gb18030")
    parser.add_argument("--allow-host", action="append", default=[], help="Exact lowercase image hostname verified from an actual native upload; repeat for multiple hosts")
    args = parser.parse_args(argv)
    try:
        manifest = convert_file(args.literal_txt or args.article, args.output, args.allow_host,
                                literal_txt=args.literal_txt is not None, encoding=args.encoding)
    except ValidationError as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"state": manifest["state"], "baseline": manifest["baseline"],
                      "fragment_sha256": manifest["fragment_sha256"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
