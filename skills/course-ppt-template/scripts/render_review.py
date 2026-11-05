#!/usr/bin/env python3
"""Render a PPTX for human review without editing its content or source fonts.

LibreOffice and Poppler must be available. Pillow is optional (contact sheet).
All paths and renderer/font substitutions are recorded in review.json.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def executable(name: str, explicit: str | None = None) -> str:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Executable does not exist: {path}")
        return str(path)
    found = shutil.which(name)
    if found:
        return found
    home = Path.home()
    candidates = [
        home / ".cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override" / name,
        home / ".dsh/dsh-runtimes/dsh-primary-runtime/dependencies/bin/override" / name,
        Path("/opt/homebrew/bin") / name,
        Path("/usr/bin") / name,
    ]
    if name == "soffice":
        candidates.append(Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"))
    for path in candidates:
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    raise ValueError(f"Missing {name}; install LibreOffice/Poppler or pass --{name}.")


def pages_arg(value: str | None) -> list[int] | None:
    if value is None:
        return None
    pages: set[int] = set()
    for item in value.split(","):
        if not re.fullmatch(r"\d+(?:-\d+)?", item):
            raise ValueError("--pages accepts page numbers/ranges, e.g. 1,3-5")
        first, _, last = item.partition("-")
        start, end = int(first), int(last or first)
        if start < 1 or end < start or end > 10000:
            raise ValueError("Invalid page range")
        pages.update(range(start, end + 1))
    return sorted(pages)


def fonts_config(out: Path, font_file: str | None) -> dict:
    """Use local font data only. Font aliases affect previews, never the PPTX."""
    folders = [Path("/System/Library/Fonts"), Path("/System/Library/Fonts/Supplemental"),
               Path("/Library/Fonts"), Path.home() / "Library/Fonts",
               Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
               Path.home() / ".local/share/fonts"]
    chosen: Path | None = None
    if font_file:
        chosen = Path(font_file).expanduser().resolve()
        if not chosen.is_file():
            raise ValueError(f"Font file does not exist: {chosen}")
    elif sys.platform == "darwin":
        chosen = next(Path("/System/Library/AssetsV2").glob(
            "com_apple_MobileAsset_Font*/**/PingFang.ttc"), None)
    if chosen:
        folders.append(chosen.parent)
    root = ET.Element("fontconfig")
    for directory in dict.fromkeys(folders):
        if directory.is_dir():
            ET.SubElement(root, "dir").text = str(directory)
    ET.SubElement(root, "cachedir").text = str(out / ".fontcache")
    # Exact source fonts take precedence if installed. These aliases only add
    # fallbacks so headless renderers do not silently omit Chinese glyphs.
    families = ("微软雅黑", "Microsoft YaHei", "HarmonyOS Sans SC", "sans-serif")
    fallback = ["PingFang SC", "Heiti SC", "Noto Sans CJK SC", "WenQuanYi Zen Hei", "Arial Unicode MS"]
    for family in families:
        alias = ET.SubElement(root, "alias")
        ET.SubElement(alias, "family").text = family
        prefer = ET.SubElement(alias, "prefer")
        for name in fallback:
            ET.SubElement(prefer, "family").text = name
    target = out / "fonts.conf"
    target.write_bytes(b'<?xml version="1.0"?>\n<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
                       + ET.tostring(root, encoding="utf-8"))
    return {
        "config": str(target),
        "local_font_file": str(chosen) if chosen else None,
        "fallback_families": fallback,
        "note": "Preview may substitute missing fonts. Source PPTX fonts are unchanged; verify target-app appearance separately.",
    }


def run(command: list[str], env: dict, timeout: int) -> str:
    result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError(f"{Path(command[0]).name} exited {result.returncode}: "
                           f"{result.stderr[-3000:]} {result.stdout[-1000:]}")
    return result.stdout + result.stderr


def page_number(path: Path) -> int:
    return int(path.stem.rsplit("-", 1)[1])


def contact_sheet(pngs: list[Path], out: Path) -> str | None:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    width, height, label = 560, 315, 26
    columns = 2 if len(pngs) > 1 else 1
    rows = (len(pngs) + columns - 1) // columns
    # A contact sheet is a composition of existing slide renders, not artwork.
    sheet = Image.new("RGB", (width * columns, (height + label) * rows), "#E8E8E8")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(pngs):
        with Image.open(path) as image:
            thumb = image.convert("RGB")
            thumb.thumbnail((width, height))
        x = (index % columns) * width
        y = (index // columns) * (height + label)
        draw.text((x + 8, y + 6), f"Slide {page_number(path)}", fill="black")
        sheet.paste(thumb, (x, y + label))
    target = out / "contact-sheet.png"
    sheet.save(target)
    return str(target)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pptx", help="PPTX to inspect (never modified)")
    parser.add_argument("--out", help="Review directory; default: <stem>-review")
    parser.add_argument("--pages", help="Optional 1-based pages/ranges, e.g. 1,3-5")
    parser.add_argument("--font-file", help="Optional local font file to expose to Fontconfig")
    parser.add_argument("--soffice", help="LibreOffice executable")
    parser.add_argument("--pdftoppm", help="Poppler pdftoppm executable")
    parser.add_argument("--size", type=int, default=1400, help="Longest PNG edge in pixels")
    parser.add_argument("--timeout", type=int, default=240, help="Per-renderer timeout in seconds")
    args = parser.parse_args()
    source = Path(args.pptx).expanduser().resolve()
    if not source.is_file() or source.suffix.lower() != ".pptx":
        raise ValueError(f"Input must be an existing .pptx file: {source}")
    if not 300 <= args.size <= 5000 or not 10 <= args.timeout <= 1800:
        raise ValueError("--size must be 300–5000; --timeout must be 10–1800")
    pages = pages_arg(args.pages)
    out = Path(args.out).expanduser().resolve() if args.out else source.with_name(source.stem + "-review")
    out.mkdir(parents=True, exist_ok=True)
    # Distinct conversion directory prevents collisions with a source PDF or
    # stale PNGs in previous reviews. Only this run's paths enter review.json.
    render_dir = Path(tempfile.mkdtemp(prefix="render-", dir=out))
    font_info = fonts_config(out, args.font_file)
    env = os.environ.copy()
    env["FONTCONFIG_FILE"] = font_info["config"]
    soffice, poppler = executable("soffice", args.soffice), executable("pdftoppm", args.pdftoppm)
    print("Rendering PDF with local font fallback…", file=sys.stderr, flush=True)
    with tempfile.TemporaryDirectory(prefix="course-ppt-lo-") as profile:
        log = run([soffice, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless",
                   "--convert-to", "pdf:impress_pdf_Export", "--outdir", str(render_dir), str(source)],
                  env, args.timeout)
    pdf = render_dir / (source.stem + ".pdf")
    if not pdf.is_file() or pdf.stat().st_size < 100:
        raise RuntimeError(f"LibreOffice produced no PDF: {log[-2000:]}")
    print("Rendering slide PNGs…", file=sys.stderr, flush=True)
    prefix = render_dir / "slide"
    if pages:
        for page in pages:
            run([poppler, "-f", str(page), "-l", str(page), "-scale-to", str(args.size),
                 "-png", str(pdf), str(prefix)], env, args.timeout)
    else:
        run([poppler, "-scale-to", str(args.size), "-png", str(pdf), str(prefix)], env, args.timeout)
    pngs = sorted(render_dir.glob("slide-*.png"), key=page_number)
    if not pngs or (pages and [page_number(p) for p in pngs] != pages):
        raise RuntimeError("PNG page coverage does not match requested pages")
    sheet = contact_sheet(pngs, render_dir)
    report = {
        "source": str(source), "pdf": str(pdf), "rendered_pages": [page_number(p) for p in pngs],
        "pngs": [str(p) for p in pngs], "contact_sheet": sheet,
        "renderer": "LibreOffice + Poppler", "soffice": soffice, "pdftoppm": poppler,
        "fonts": font_info, "human_visual_review_required": True,
        "scope": "Render availability only; does not establish content accuracy, layout quality, or target-app fidelity.",
    }
    report_path = out / "review.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"review": str(report_path), "pages": len(pngs), "contact_sheet": sheet}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, RuntimeError, subprocess.TimeoutExpired, OSError) as error:
        print(f"Review failed: {error}", file=sys.stderr)
        raise SystemExit(1)
