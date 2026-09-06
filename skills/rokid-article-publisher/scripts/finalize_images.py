#!/usr/bin/env python3
"""Validate UI-obtained Rokid image mappings and finalize Markdown, offline."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


PLACEHOLDER = re.compile(r"\{\{RK_IMAGE_\d{4,}\}\}")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
HOST = re.compile(r"(?=.{1,253}\Z)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
DEFAULT_HOST_SUFFIXES = ()


class ValidationError(Exception):
    """Safe diagnostic: messages must not include URLs or source contents."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValidationError("JSON contains a duplicate key")
        result[key] = value
    return result


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except ValidationError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError):
        raise ValidationError("Cannot read valid UTF-8 JSON input") from None


def _valid_sha(value):
    return isinstance(value, str) and SHA256.fullmatch(value) is not None


def validate_url(value, extra_hosts=()):
    """Return the original URL, without stripping or rewriting its query."""
    if not isinstance(value, str) or not value or len(value) > 16384:
        raise ValidationError("Hosted image URL is missing or invalid")
    # These raw characters can inject Markdown/HTML or make parsers disagree.
    if any(c.isspace() or ord(c) < 33 or ord(c) == 127 or c in '<>\\\"`{}()[]' for c in value):
        raise ValidationError("Hosted image URL contains unsafe raw characters")
    try:
        parts = urlsplit(value)
        host = parts.hostname
        port = parts.port
        user = parts.username
        password = parts.password
    except ValueError:
        raise ValidationError("Hosted image URL cannot be parsed safely") from None
    if parts.scheme != "https" or not parts.netloc or not host or user is not None or password is not None:
        raise ValidationError("Hosted image URL must use HTTPS without user information")
    if port not in (None, 443):
        raise ValidationError("Hosted image URL must use the default HTTPS port")
    if not HOST.fullmatch(host) or host.endswith("."):
        raise ValidationError("Hosted image URL host is invalid")
    if not any(host == suffix or host.endswith("." + suffix) for suffix in DEFAULT_HOST_SUFFIXES) and host not in extra_hosts:
        raise ValidationError("Hosted image URL host is not allowed; verify the actual upload host before allowing it")
    if not parts.path or parts.path == "/":
        raise ValidationError("Hosted image URL must point to an image resource")
    return value


def validate_extra_hosts(hosts):
    result = set()
    for host in hosts:
        if not isinstance(host, str) or not HOST.fullmatch(host) or host != host.lower():
            raise ValidationError("--allow-host requires one exact lowercase hostname, without scheme, path, wildcard or port")
        result.add(host)
    return result


def finalize_bytes(article, manifest, mapping, base_dir, extra_hosts=()):
    """Prevalidate everything; return bytes with only placeholders replaced."""
    if not isinstance(article, bytes):
        raise ValidationError("Article input must be bytes")
    try:
        article_text = article.decode("utf-8")
    except UnicodeError:
        raise ValidationError("Article must be valid UTF-8") from None
    if not isinstance(manifest, dict) or type(manifest.get("schema_version")) is not int or manifest.get("schema_version") != 1:
        raise ValidationError("Unsupported manifest schema_version")
    baseline = manifest.get("baseline")
    if not isinstance(baseline, dict) or not _valid_sha(baseline.get("prepared_markdown_sha256")):
        raise ValidationError("Manifest needs a valid prepared Markdown SHA-256 baseline; prepare the source again")
    if hashlib.sha256(article).hexdigest() != baseline["prepared_markdown_sha256"]:
        raise ValidationError("Article changed after preparation; edit the source and prepare it again")
    if not isinstance(manifest.get("blocking_issues"), list):
        raise ValidationError("Manifest must contain a blocking_issues list")
    if manifest["blocking_issues"]:
        raise ValidationError("Manifest has blocking issues; resolve them and prepare the source again")
    images = manifest.get("images")
    if not isinstance(images, list) or not isinstance(mapping, dict):
        raise ValidationError("Manifest images must be a list and hosted map must be an object")
    extra_hosts = validate_extra_hosts(extra_hosts)
    expected = {}
    base_dir = Path(base_dir).resolve()
    for index, image in enumerate(images, 1):
        if not isinstance(image, dict) or image.get("order") != index or isinstance(image.get("order"), bool):
            raise ValidationError("Manifest image order must be contiguous and one-based")
        key = image.get("placeholder")
        if key != "{{RK_IMAGE_%04d}}" % index or key in expected:
            raise ValidationError("Manifest image placeholders must be unique and match their order")
        if image.get("kind") != "local" or not _valid_sha(image.get("sha256")):
            raise ValidationError("Only prepared local images with verified SHA-256 may be finalized")
        relative = image.get("relative_path")
        if not isinstance(relative, str) or not relative or "\\" in relative:
            raise ValidationError("Manifest image path is invalid")
        relpath = Path(relative)
        if relpath.is_absolute() or ".." in relpath.parts:
            raise ValidationError("Manifest image path must remain inside the prepared directory")
        try:
            candidate = (base_dir / relpath).resolve(strict=True)
            candidate.relative_to(base_dir)
            if not candidate.is_file():
                raise ValidationError("Prepared image is not a regular file")
            digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except (OSError, ValueError):
            raise ValidationError("Prepared image is missing, unreadable, or outside the prepared directory") from None
        if digest != image["sha256"]:
            raise ValidationError("Prepared image changed after inventory; prepare it again")
        expected[key] = image
    found = PLACEHOLDER.findall(article_text)
    if len(found) != len(set(found)):
        raise ValidationError("Article contains a repeated image placeholder")
    if set(found) != set(expected):
        raise ValidationError("Article image placeholders do not exactly match the manifest")
    # Catch malformed placeholders which the strict matcher would miss.
    without = PLACEHOLDER.sub("", article_text)
    if "{{RK_IMAGE_" in without:
        raise ValidationError("Article contains a malformed image placeholder")
    if found != list(expected):
        raise ValidationError("Article image order does not match the manifest")
    if set(mapping) != set(expected):
        raise ValidationError("Hosted map must contain exactly one entry for every manifest image")
    replacements = {}
    url_sources = {}
    for key, image in expected.items():
        entry = mapping[key]
        if not isinstance(entry, dict) or set(entry) - {"url", "source_sha256"} or "url" not in entry:
            raise ValidationError("Each hosted map entry must contain url and optional source_sha256 only")
        digest = entry.get("source_sha256")
        if digest is not None and (not _valid_sha(digest) or digest != image["sha256"]):
            raise ValidationError("Hosted map source_sha256 does not match the prepared image")
        url = validate_url(entry["url"], extra_hosts)
        previous = url_sources.get(url)
        if previous is not None and previous != image["sha256"]:
            raise ValidationError("Different source images unexpectedly share one hosted URL")
        url_sources[url] = image["sha256"]
        replacements[key.encode("ascii")] = url.encode("utf-8")
    pattern = re.compile(rb"\{\{RK_IMAGE_\d{4,}\}\}")
    return pattern.sub(lambda match: replacements[match.group(0)], article)


def write_new_file(path, content):
    """Create a new file atomically; existing paths and symlinks never get replaced."""
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix=".rokid-finalize-", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    except FileExistsError:
        raise ValidationError("Output already exists; choose a new output filename") from None
    except OSError:
        raise ValidationError("Cannot create the new output file") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--article", required=True, type=Path)
    parser.add_argument("--hosted-map", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--allow-host", action="append", default=[], help="Exact upload hostname verified in the UI; repeat if needed")
    args = parser.parse_args(argv)
    try:
        manifest = read_json(args.manifest)
        mapping = read_json(args.hosted_map)
        try:
            article = args.article.read_bytes()
        except OSError:
            raise ValidationError("Cannot read article input") from None
        result = finalize_bytes(article, manifest, mapping, args.manifest.parent, args.allow_host)
        write_new_file(args.output, result)
    except ValidationError as error:
        print("Validation failed: " + str(error), file=sys.stderr)
        return 2
    print(json.dumps({"status": "ready_for_editor", "images": len(manifest["images"]), "bytes": len(result), "sha256": hashlib.sha256(result).hexdigest()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
