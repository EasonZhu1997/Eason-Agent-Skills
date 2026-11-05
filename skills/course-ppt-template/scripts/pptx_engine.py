#!/usr/bin/env python3
"""Clone editable OOXML template slides without a presentation library.

All layout choices live in a separate JSON profile.  The model supplies text,
never coordinates, fonts, colours, XML, or replacement artwork.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import posixpath
import re
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
MC = "http://schemas.openxmlformats.org/markup-compatibility/2006"
NS = {"p": P, "a": A, "r": R}
SLIDE_TYPE = R + "/slide"
SLIDE_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.presentationml.slide+xml"
MANIFEST = "course-template-manifest.json"


class DeckError(ValueError):
    pass


def parse(data):
    return ET.fromstring(data)


def xml_bytes(root, original=None):
    """Keep original namespace names, including unused mc:Ignorable names."""
    nsmap = []
    if original:
        for event, item in ET.iterparse(io.BytesIO(original), events=("start-ns",)):
            if item not in nsmap:
                nsmap.append(item)
    for prefix, uri in [("p", P), ("a", A), ("r", R), ("mc", MC), *nsmap]:
        if not re.fullmatch(r"ns\d+", prefix):
            ET.register_namespace(prefix, uri)
    result = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    # ET drops declarations unused in qualified names.  mc:Ignorable refers to
    # namespace prefixes as string values, so restore those declarations.
    start = result.find(b"?>") + 2
    close = result.find(b">", start)
    tag = result[start:close]
    inserts = []
    from xml.sax.saxutils import quoteattr
    for prefix, uri in nsmap:
        name = ("xmlns:" + prefix) if prefix else "xmlns"
        if not re.search(rb"(?:\s)" + re.escape(name.encode()) + rb"=", tag):
            inserts.append(" " + name + "=" + quoteattr(uri))
    if inserts:
        result = result[:close] + "".join(inserts).encode() + result[close:]
    return result


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def read_package(path):
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        if corrupt:
            raise DeckError(f"Corrupt ZIP entry: {corrupt}")
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise DeckError("Duplicate ZIP entry names")
        return {name: archive.read(name) for name in names if not name.endswith("/")}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_package(parts, output, force=False):
    output = Path(output)
    if output.exists() and not force:
        raise DeckError(f"Output exists; choose a new name or use --force: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".pptx-", suffix=".tmp", dir=output.parent)
    try:
        with os.fdopen(fd, "wb") as stream, zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for name, data in sorted(parts.items()):
                info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, data)
        os.replace(temporary, output)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def rels_name(part):
    if part == "":
        return "_rels/.rels"
    directory, filename = posixpath.split(part)
    return posixpath.join(directory, "_rels", filename + ".rels")


def rels_owner(name):
    if name == "_rels/.rels":
        return ""
    directory, filename = posixpath.split(name)
    if posixpath.basename(directory) != "_rels" or not filename.endswith(".rels"):
        raise DeckError(f"Invalid relationship part name: {name}")
    return posixpath.join(posixpath.dirname(directory), filename[:-5])


def resolve_target(owner, target):
    if not target or "\\" in target:
        raise DeckError(f"Invalid relationship target: {target!r}")
    from urllib.parse import unquote, urlsplit
    split = urlsplit(target)
    if split.scheme or split.netloc:
        raise DeckError(f"Internal relationship has external target: {target!r}")
    target = unquote(split.path)
    resolved = posixpath.normpath(target.lstrip("/") if target.startswith("/") else posixpath.join(posixpath.dirname(owner), target))
    if resolved.startswith("../") or resolved in (".", ".."):
        raise DeckError(f"Relationship escapes package: {target!r}")
    return resolved


def relative_target(owner, target):
    return posixpath.relpath(target, posixpath.dirname(owner) or ".")


def load_profile(path):
    profile = read_json(path)
    if profile.get("version") != 1 or not isinstance(profile.get("layouts"), dict) or not profile["layouts"]:
        raise DeckError("Profile needs version=1 and a nonempty layouts object")
    if len(profile.get("slide_size", [])) != 2:
        raise DeckError("Profile needs slide_size=[cx,cy]")
    source_slides = []
    for layout, definition in profile["layouts"].items():
        if not isinstance(definition.get("slide"), int) or definition["slide"] < 1:
            raise DeckError(f"{layout}: positive source slide number required")
        source_slides.append(definition["slide"])
        slots = definition.get("slots")
        if not isinstance(slots, dict) or not slots:
            raise DeckError(f"{layout}: nonempty slots required")
        ids = []
        for key, spec in slots.items():
            if "shape_id" not in spec or not isinstance(spec.get("max_chars"), int) or spec["max_chars"] < 1:
                raise DeckError(f"{layout}/{key}: shape_id and positive max_chars required")
            if "max_chars_per_line" in spec and (not isinstance(spec["max_chars_per_line"], int) or spec["max_chars_per_line"] < 1):
                raise DeckError(f"{layout}/{key}: max_chars_per_line must be positive")
            ids.append(str(spec["shape_id"]))
            if spec.get("auto") not in (None, "@course", "@page", "@required"):
                raise DeckError(f"{layout}/{key}: unsupported auto value")
        if len(set(ids)) != len(ids):
            raise DeckError(f"{layout}: more than one slot addresses the same shape")
    if len(set(source_slides)) != len(source_slides):
        raise DeckError("Each layout must have a distinct source slide")
    return profile


def shape_id(shape):
    node = shape.find("p:nvSpPr/p:cNvPr", NS)
    return node.get("id") if node is not None else None


def shapes(root):
    return {shape_id(s): s for s in root.findall(".//p:sp", NS)}


def shape_text(shape):
    body = shape.find("p:txBody", NS)
    if body is None:
        return ""
    return "\n".join("".join(t.text or "" for t in p.findall(".//a:t", NS)) for p in body.findall("a:p", NS))


def remove_shapes(root, ids):
    ids = {str(x) for x in ids}
    found = set()
    for parent in root.iter():
        for child in list(parent):
            if child.tag == f"{{{P}}}sp" and shape_id(child) in ids:
                found.add(shape_id(child))
                parent.remove(child)
    if found != ids:
        raise DeckError(f"remove_shapes refers to absent shapes: {sorted(ids - found)}")


def check_coverage(root, definition, layout):
    all_shapes = shapes(root)
    specified = {str(s["shape_id"]) for s in definition["slots"].values()}
    preserved = {str(s) for s in definition.get("preserve_shapes", [])}
    if specified & preserved:
        raise DeckError(f"{layout}: slots and preserve_shapes overlap")
    missing = specified - all_shapes.keys()
    if missing:
        raise DeckError(f"{layout}: slot shapes absent: {sorted(missing)}")
    uncovered = {i for i, shape in all_shapes.items() if shape_text(shape).strip()} - specified - preserved
    if uncovered:
        raise DeckError(f"{layout}: uncovered text shapes: {sorted(uncovered)}")
    # Tables and charts need explicit support, rather than silently retaining
    # source course text that cannot be addressed by the profile's shape slots.
    outside = []
    shape_elements = {id(e) for s in all_shapes.values() for e in s.iter()}
    for t in root.findall(".//a:t", NS):
        if id(t) not in shape_elements and (t.text or "").strip():
            outside.append(t.text)
    if outside:
        raise DeckError(f"{layout}: non-shape text needs explicit support: {outside[:3]}")


def forbidden_relationship(rel):
    kind = rel.get("Type", "").rsplit("/", 1)[-1]
    return rel.get("TargetMode") == "External" or kind in {
        "notesSlide", "notesMaster", "comments", "commentAuthors", "person",
        "threadedComment", "handoutMaster", "audio", "video", "media",
        "custom-properties", "tags", "vbaProject", "oleObject", "package",
        "customXml", "customXmlProps",
    }


def clean_relationship_references(data, removed):
    if not removed:
        return data
    root = parse(data)
    for parent in root.iter():
        for child in list(parent):
            if child.tag in (f"{{{A}}}hlinkClick", f"{{{A}}}hlinkMouseOver", f"{{{P}}}tags") and child.get(f"{{{R}}}id") in removed:
                parent.remove(child)
            elif any(value in removed for key, value in child.attrib.items() if key.startswith("{" + R + "}")):
                raise DeckError(f"Unsupported object references a removed relationship: {child.tag}")
    return xml_bytes(root, data)


def clear_inherited_text(data):
    root = parse(data)
    for t in root.findall(".//a:t", NS):
        t.text = ""
    return xml_bytes(root, data)


def sanitize_metadata(data):
    """Discard source prose/code hidden in alt text and object labels.

    Some authoring exporters put complete source JSX in cNvPr/@descr,
    including group nonvisual properties.  These attributes are not visible
    slide content and must never become a second copy of a previous lesson.
    """
    root = parse(data)
    for node in root.iter():
        for key in list(node.attrib):
            if key.rsplit("}", 1)[-1] in {"descr", "title", "tooltip"}:
                del node.attrib[key]
        if node.tag.rsplit("}", 1)[-1] == "cNvPr":
            node.set("name", "Shape " + node.get("id", "0"))
        elif node.tag == f"{{{P}}}cSld":
            node.attrib.pop("name", None)
    return xml_bytes(root, data)


def set_slide_list(presentation, relations, slide_names):
    rel_root = parse(relations)
    for rel in list(rel_root):
        if rel.get("Type") == SLIDE_TYPE or forbidden_relationship(rel):
            rel_root.remove(rel)
    used = {r.get("Id") for r in rel_root}
    root = parse(presentation)
    sld_list = root.find("p:sldIdLst", NS)
    if sld_list is None:
        sld_list = ET.Element(f"{{{P}}}sldIdLst")
        root.insert(1, sld_list)
    else:
        sld_list.clear()
    index = 1
    for i, name in enumerate(slide_names, 256):
        while "rId" + str(index) in used:
            index += 1
        rid = "rId" + str(index)
        used.add(rid)
        ET.SubElement(rel_root, f"{{{PKG}}}Relationship", {"Id": rid, "Type": SLIDE_TYPE, "Target": relative_target("ppt/presentation.xml", name)})
        ET.SubElement(sld_list, f"{{{P}}}sldId", {"id": str(i), f"{{{R}}}id": rid})
    for child in list(root):
        if child.tag.rsplit("}", 1)[-1] in {"notesMasterIdLst", "handoutMasterIdLst", "custShowLst"}:
            root.remove(child)
        # Old sections refer to old slide IDs.
        if child.tag == f"{{{P}}}extLst":
            root.remove(child)
    return xml_bytes(root, presentation), xml_bytes(rel_root, relations)


def prune(parts):
    """Retain parts reachable through package relationships, fail on bad targets."""
    output = {}
    queue = [""]
    seen = set()
    while queue:
        owner = queue.pop()
        if owner in seen:
            continue
        seen.add(owner)
        if owner:
            if owner not in parts:
                raise DeckError(f"Missing relationship target: {owner}")
            output[owner] = parts[owner]
        rn = rels_name(owner)
        if rn not in parts:
            continue
        original = parts[rn]
        root = parse(original)
        removed = set()
        for rel in list(root):
            if forbidden_relationship(rel) or (rel.get("Type") == SLIDE_TYPE and owner != "ppt/presentation.xml"):
                removed.add(rel.get("Id"))
                root.remove(rel)
                continue
            target = resolve_target(owner, rel.get("Target", ""))
            if target not in parts:
                raise DeckError(f"{rn}: dangling target {target}")
            queue.append(target)
        output[rn] = xml_bytes(root, original)
        if owner and removed and owner.endswith(".xml"):
            output[owner] = clean_relationship_references(output[owner], removed)
    # The JSON provenance manifest is a deliberate package-level extra part.
    if MANIFEST in parts:
        output[MANIFEST] = parts[MANIFEST]
    output["[Content_Types].xml"] = content_types(parts["[Content_Types].xml"], output)
    return output


def content_types(original, parts):
    root = parse(original)
    for node in list(root):
        if node.tag == f"{{{CT}}}Override" and node.get("PartName", "").lstrip("/") not in parts:
            root.remove(node)
    present = {x.get("PartName", "").lstrip("/") for x in root if x.tag == f"{{{CT}}}Override"}
    for name in parts:
        if re.fullmatch(r"ppt/slides/slide\d+\.xml", name) and name not in present:
            ET.SubElement(root, f"{{{CT}}}Override", {"PartName": "/" + name, "ContentType": SLIDE_CONTENT_TYPE})
    if MANIFEST in parts and MANIFEST not in present:
        ET.SubElement(root, f"{{{CT}}}Override", {"PartName": "/" + MANIFEST, "ContentType": "application/json"})
    return xml_bytes(root, original)


def check_dimensions(parts, profile):
    size = parse(parts["ppt/presentation.xml"]).find("p:sldSz", NS)
    actual = [int(size.get("cx")), int(size.get("cy"))] if size is not None else None
    if actual != profile["slide_size"]:
        raise DeckError(f"Slide size mismatch: {actual} != {profile['slide_size']}")


def update_metadata(parts, title, count):
    for name in ["docProps/core.xml", "docProps/app.xml"]:
        if name not in parts:
            continue
        original = parts[name]
        root = parse(original)
        # Source authorship fields, titles-of-parts and arbitrary custom
        # properties are not reusable course content. Rebuild minimal metadata.
        for node in list(root):
            root.remove(node)
        if name.endswith("core.xml"):
            ET.SubElement(root, "{http://purl.org/dc/elements/1.1/}title").text = title
            ET.SubElement(root, "{http://purl.org/dc/elements/1.1/}creator").text = "course-ppt-template"
        else:
            app_ns = root.tag.split("}", 1)[0] + "}"
            ET.SubElement(root, app_ns + "Application").text = "course-ppt-template"
            ET.SubElement(root, app_ns + "Slides").text = str(count)
            ET.SubElement(root, app_ns + "Notes").text = "0"
        parts[name] = xml_bytes(root, original)


def bootstrap(args):
    if Path(args.source).resolve() == Path(args.output).resolve():
        raise DeckError("Source and output must differ")
    profile = load_profile(args.profile)
    source = read_package(args.source)
    check_dimensions(source, profile)
    parts = dict(source)
    selected = []
    # Read all source slides before writing renamed slide parts, avoiding aliases.
    chosen = []
    for name, definition in profile["layouts"].items():
        old = f"ppt/slides/slide{definition['slide']}.xml"
        if old not in source:
            raise DeckError(f"{name}: source slide missing: {old}")
        chosen.append((name, definition, old, source[old], source.get(rels_name(old))))
    for i, (name, definition, old, data, rels) in enumerate(chosen, 1):
        new = f"ppt/slides/slide{i}.xml"
        root = parse(data)
        remove_shapes(root, definition.get("remove_shapes", []))
        check_coverage(root, definition, name)
        parts[new] = xml_bytes(root, data)
        if rels:
            parts[rels_name(new)] = rels
        else:
            parts.pop(rels_name(new), None)
        selected.append(new)
    parts["ppt/presentation.xml"], parts["ppt/_rels/presentation.xml.rels"] = set_slide_list(source["ppt/presentation.xml"], source["ppt/_rels/presentation.xml.rels"], selected)
    for name in list(parts):
        if re.fullmatch(r"ppt/(slideLayouts|slideMasters)/[^/]+\.xml", name):
            parts[name] = clear_inherited_text(parts[name])
    parts[MANIFEST] = json.dumps({"version": 1, "metadata_sanitized": 1, "source_sha256": sha(Path(args.source).read_bytes()), "profile_sha256": sha(Path(args.profile).read_bytes()), "layouts": list(profile["layouts"]), "source_slides": [d["slide"] for d in profile["layouts"].values()]}, ensure_ascii=False, indent=2).encode()
    parts = prune(parts)
    for name in list(parts):
        if name.endswith(".xml") and name != "[Content_Types].xml":
            parts[name] = sanitize_metadata(parts[name])
    update_metadata(parts, "Course template", len(selected))
    validate_relationships(parts)
    write_package(parts, args.output, args.force)
    return {"status": "ok", "output": str(Path(args.output).resolve()), "layouts": list(profile["layouts"]), "parts": len(parts), "bytes": Path(args.output).stat().st_size, "sha256": sha(Path(args.output).read_bytes())}


def resolve_content(profile, content):
    if not isinstance(content, dict) or set(content) != {"title", "slides"}:
        raise DeckError("Content root must contain exactly title and slides")
    title = content.get("title")
    if not isinstance(title, str) or not title.strip():
        raise DeckError("Nonblank course title required")
    slides = content.get("slides")
    if not isinstance(slides, list) or not 1 <= len(slides) <= 500:
        raise DeckError("Content needs 1..500 slides")
    resolved = []
    for i, slide in enumerate(slides, 1):
        if not isinstance(slide, dict) or set(slide) != {"layout", "slots"}:
            raise DeckError(f"Slide {i}: expected exactly layout and slots")
        name = slide["layout"]
        if name not in profile["layouts"]:
            raise DeckError(f"Slide {i}: unknown layout {name!r}")
        specs = profile["layouts"][name]["slots"]
        supplied = slide["slots"]
        if not isinstance(supplied, dict):
            raise DeckError(f"Slide {i}: slots must be an object")
        expected = {key for key, spec in specs.items() if not spec.get("auto")}
        if set(supplied) != expected:
            raise DeckError(f"Slide {i} ({name}): missing slots {sorted(expected - set(supplied))}; extra slots {sorted(set(supplied) - expected)}")
        values = {}
        for key, spec in specs.items():
            value = {"@course": title, "@page": f"{i} / {len(slides)}", "@required": "必讲"}.get(spec.get("auto")) if spec.get("auto") else supplied[key]
            if not isinstance(value, str) or not value.strip():
                raise DeckError(f"Slide {i}/{key}: text must be a nonblank string")
            if any(ord(c) < 32 and c not in "\n\t" for c in value):
                raise DeckError(f"Slide {i}/{key}: unsupported control character")
            if len(value) > spec["max_chars"]:
                raise DeckError(f"Slide {i}/{key}: {len(value)} characters exceeds {spec['max_chars']}")
            if len(value.split("\n")) > spec.get("max_lines", 1):
                raise DeckError(f"Slide {i}/{key}: exceeds {spec.get('max_lines', 1)} lines")
            for line_number, line in enumerate(value.split("\n"), 1):
                if len(line) > spec.get("max_chars_per_line", spec["max_chars"]):
                    raise DeckError(f"Slide {i}/{key}: line {line_number} exceeds {spec['max_chars_per_line']} characters per line")
            if any(not line.strip() for line in value.split("\n")):
                raise DeckError(f"Slide {i}/{key}: blank lines are not supported")
            values[key] = value
        resolved.append((name, values))
    return resolved


def replace_text(shape, value):
    body = shape.find("p:txBody", NS)
    if body is None:
        raise DeckError(f"Shape {shape_id(shape)} has no editable text body")
    old = body.findall("a:p", NS)
    first = old[0] if old else ET.Element(f"{{{A}}}p")
    for p in old:
        body.remove(p)
    for i, line in enumerate(value.split("\n")):
        source = old[min(i, len(old) - 1)] if old else first
        paragraph = ET.SubElement(body, f"{{{A}}}p")
        ppr = source.find("a:pPr", NS)
        if ppr is not None:
            paragraph.append(copy.deepcopy(ppr))
        run = ET.SubElement(paragraph, f"{{{A}}}r")
        rpr = source.find("a:r/a:rPr", NS)
        if rpr is None:
            rpr = source.find("a:fld/a:rPr", NS)
        if rpr is None:
            rpr = source.find("a:endParaRPr", NS)
        if rpr is not None:
            clone = copy.deepcopy(rpr)
            clone.tag = f"{{{A}}}rPr"
            for link in list(clone):
                if link.tag.rsplit("}", 1)[-1] in {"hlinkClick", "hlinkMouseOver"}:
                    clone.remove(link)
            run.append(clone)
        text = ET.SubElement(run, f"{{{A}}}t")
        text.text = line
        if line != line.strip():
            text.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        end = source.find("a:endParaRPr", NS)
        if end is not None:
            paragraph.append(copy.deepcopy(end))
    props = body.find("a:bodyPr", NS)
    if props is None:
        props = ET.Element(f"{{{A}}}bodyPr")
        body.insert(0, props)
    for child in list(props):
        if child.tag.rsplit("}", 1)[-1] in {"spAutoFit", "normAutofit", "noAutofit"}:
            props.remove(child)
    ET.SubElement(props, f"{{{A}}}noAutofit")


def check_template(parts, profile, profile_path):
    check_dimensions(parts, profile)
    if MANIFEST not in parts:
        raise DeckError("Template has no manifest; run bootstrap first")
    manifest = json.loads(parts[MANIFEST])
    if manifest.get("metadata_sanitized") != 1:
        raise DeckError("Legacy template cache may contain source metadata; run bootstrap again")
    if manifest.get("profile_sha256") != sha(Path(profile_path).read_bytes()) or manifest.get("layouts") != list(profile["layouts"]):
        raise DeckError("Template/profile mismatch; bootstrap again with this profile")


def build(args):
    if Path(args.template).resolve() == Path(args.output).resolve():
        raise DeckError("Template and output must differ")
    profile = load_profile(args.profile)
    content = read_json(args.content)
    resolved = resolve_content(profile, content)
    template = read_package(args.template)
    check_template(template, profile, args.profile)
    parts = dict(template)
    selected = []
    indices = {name: i for i, name in enumerate(profile["layouts"], 1)}
    for i, (name, values) in enumerate(resolved, 1):
        old = f"ppt/slides/slide{indices[name]}.xml"
        new = f"ppt/slides/slide{i}.xml"
        data = template[old]
        root = parse(data)
        check_coverage(root, profile["layouts"][name], name)
        ss = shapes(root)
        for key, value in values.items():
            replace_text(ss[str(profile["layouts"][name]["slots"][key]["shape_id"])], value)
        parts[new] = xml_bytes(root, data)
        rn = rels_name(old)
        if rn in template:
            parts[rels_name(new)] = template[rn]
        else:
            parts.pop(rels_name(new), None)
        selected.append(new)
    parts["ppt/presentation.xml"], parts["ppt/_rels/presentation.xml.rels"] = set_slide_list(template["ppt/presentation.xml"], template["ppt/_rels/presentation.xml.rels"], selected)
    parts[MANIFEST] = json.dumps({**json.loads(template[MANIFEST]), "content_sha256": sha(Path(args.content).read_bytes()), "template_sha256": sha(Path(args.template).read_bytes()), "output_layouts": [n for n, values in resolved]}, ensure_ascii=False, indent=2).encode()
    parts = prune(parts)
    update_metadata(parts, content["title"], len(selected))
    report = validate_parts(parts, profile, content, template)
    write_package(parts, args.output, args.force)
    return {**report, "output": str(Path(args.output).resolve()), "bytes": Path(args.output).stat().st_size, "sha256": sha(Path(args.output).read_bytes())}


def validate_relationships(parts):
    for name, data in parts.items():
        if not name.endswith(".rels"):
            continue
        owner = rels_owner(name)
        ids = set()
        for rel in parse(data):
            rid = rel.get("Id")
            if not rid or rid in ids:
                raise DeckError(f"{name}: missing or duplicate relationship ID")
            ids.add(rid)
            if forbidden_relationship(rel):
                raise DeckError(f"{name}: excluded relationship remains: {rel.get('Type')}")
            target = resolve_target(owner, rel.get("Target", ""))
            if target not in parts:
                raise DeckError(f"{name}: dangling target {target}")
        if owner and owner.endswith(".xml"):
            for element in parse(parts[owner]).iter():
                for key, value in element.attrib.items():
                    if key.startswith("{" + R + "}") and value not in ids:
                        raise DeckError(f"{owner}: XML refers to absent relationship {value}")


def layout_fingerprint(data):
    """Ignore only editable text-body internals; keep all other XML content."""
    root = parse(data)
    for body in root.findall(".//p:txBody", NS):
        for paragraph in body.findall("a:p", NS):
            body.remove(paragraph)
        props = body.find("a:bodyPr", NS)
        if props is not None:
            for child in list(props):
                if child.tag.rsplit("}", 1)[-1] in {"spAutoFit", "normAutofit", "noAutofit"}:
                    props.remove(child)
    return canonical_node(root)


def canonical_node(node):
    return (node.tag, sorted(node.attrib.items()), node.text or "", tuple(canonical_node(child) for child in node))


def typography(data, sid):
    root = parse(data)
    shape = shapes(root)[str(sid)]
    body = shape.find("p:txBody", NS)
    para = body.find("a:p", NS)
    rpr = para.find("a:r/a:rPr", NS)
    if rpr is None:
        rpr = para.find("a:fld/a:rPr", NS)
    if rpr is None:
        rpr = para.find("a:endParaRPr", NS)
    return rpr


def validate_parts(parts, profile, content, template):
    check_dimensions(parts, profile)
    resolved = resolve_content(profile, content)
    validate_relationships(parts)
    p_root = parse(parts["ppt/presentation.xml"])
    p_rels = {r.get("Id"): resolve_target("ppt/presentation.xml", r.get("Target")) for r in parse(parts["ppt/_rels/presentation.xml.rels"])}
    listed = [p_rels[s.get(f"{{{R}}}id")] for s in p_root.findall("p:sldIdLst/p:sldId", NS)]
    expected_names = [f"ppt/slides/slide{i}.xml" for i in range(1, len(resolved) + 1)]
    if listed != expected_names:
        raise DeckError("Slide count or ordering mismatch")
    actual_names = {n for n in parts if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)}
    if actual_names != set(expected_names):
        raise DeckError("Unlisted slide parts remain")
    # Shared assets and OOXML style parts are immutable. Slide-only checks do
    # not detect a changed theme, master, layout, table style or relationship.
    def dynamic_part(name):
        return name in {
            "ppt/presentation.xml", "ppt/_rels/presentation.xml.rels",
            "[Content_Types].xml", "docProps/core.xml", "docProps/app.xml",
            MANIFEST,
        } or re.fullmatch(r"ppt/slides/(?:_rels/)?slide\d+\.xml(?:\.rels)?", name)
    shared_count = 0
    for name, data in parts.items():
        if not dynamic_part(name):
            if name not in template or data != template[name]:
                raise DeckError(f"Shared template part changed: {name}")
            shared_count += 1
    expected_presentation = parse(template["ppt/presentation.xml"])
    actual_presentation = parse(parts["ppt/presentation.xml"])
    for root in [expected_presentation, actual_presentation]:
        slide_list = root.find("p:sldIdLst", NS)
        if slide_list is not None:
            root.remove(slide_list)
    if canonical_node(expected_presentation) != canonical_node(actual_presentation):
        raise DeckError("Presentation properties outside the slide list changed")
    def shared_presentation_rels(data):
        return sorted(tuple(sorted(rel.attrib.items())) for rel in parse(data) if rel.get("Type") != SLIDE_TYPE)
    if shared_presentation_rels(parts["ppt/_rels/presentation.xml.rels"]) != shared_presentation_rels(template["ppt/_rels/presentation.xml.rels"]):
        raise DeckError("Presentation shared relationships changed")
    expected_types = content_types(template["[Content_Types].xml"], parts)
    def type_entries(data):
        return sorted((node.tag, tuple(sorted(node.attrib.items()))) for node in parse(data))
    if type_entries(expected_types) != type_entries(parts["[Content_Types].xml"]):
        raise DeckError("Content types differ from the template-derived package")
    expected_metadata = {name: template[name] for name in ["docProps/core.xml", "docProps/app.xml"] if name in template}
    update_metadata(expected_metadata, content["title"], len(resolved))
    for name, data in expected_metadata.items():
        if name not in parts or canonical_node(parse(data)) != canonical_node(parse(parts[name])):
            raise DeckError(f"Generated document metadata differs: {name}")
    indices = {name: i for i, name in enumerate(profile["layouts"], 1)}
    text_count = 0
    for i, (name, values) in enumerate(resolved, 1):
        current = parts[f"ppt/slides/slide{i}.xml"]
        original = template[f"ppt/slides/slide{indices[name]}.xml"]
        if layout_fingerprint(current) != layout_fingerprint(original):
            raise DeckError(f"Slide {i}: non-text layout/background/shape changed")
        root = parse(current)
        definition = profile["layouts"][name]
        check_coverage(root, definition, name)
        ss = shapes(root)
        expected_shapes = shapes(parse(original))
        for key, value in values.items():
            sid = definition["slots"][key]["shape_id"]
            if shape_text(ss[str(sid)]) != value:
                raise DeckError(f"Slide {i}/{key}: text mismatch")
            source_style = typography(original, sid)
            actual_style = typography(current, sid)
            # The first-run format is the documented template style for a slot.
            if (ET.tostring(source_style) if source_style is not None else None) != (ET.tostring(actual_style) if actual_style is not None else None):
                raise DeckError(f"Slide {i}/{key}: font/size/style changed")
            expected_shape = expected_shapes[str(sid)]
            replace_text(expected_shape, value)
            if canonical_node(expected_shape.find("p:txBody", NS)) != canonical_node(ss[str(sid)].find("p:txBody", NS)):
                raise DeckError(f"Slide {i}/{key}: text typography/paragraph layout changed")
            text_count += 1
    for name, data in parts.items():
        if re.fullmatch(r"ppt/(slideMasters|slideLayouts)/[^/]+\.xml", name):
            if any((t.text or "").strip() for t in parse(data).findall(".//a:t", NS)):
                raise DeckError(f"Source text remains in inherited part: {name}")
        if name.startswith("ppt/media/"):
            if name not in template or data != template[name]:
                raise DeckError(f"Media changed: {name}")
    return {"status": "ok", "slides": len(resolved), "editable_text_shapes": text_count, "relationships": "valid", "geometry_background_shapes": "template-identical", "typography": "template-first-run-preserved", "media": "template-identical", "shared_template_parts": shared_count, "visual_review": "required"}


def validate(args):
    profile = load_profile(args.profile)
    template = read_package(args.template)
    check_template(template, profile, args.profile)
    report = validate_parts(read_package(args.pptx), profile, read_json(args.content), template)
    return {**report, "pptx": str(Path(args.pptx).resolve()), "sha256": sha(Path(args.pptx).read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    bootstrap_parser = commands.add_parser("bootstrap", help="Extract selected editable source layouts into a local cache")
    bootstrap_parser.add_argument("--source", required=True)
    build_parser = commands.add_parser("build", help="Fill template text slots from strictly validated JSON")
    build_parser.add_argument("--template", required=True)
    build_parser.add_argument("--content", required=True)
    validate_parser = commands.add_parser("validate", help="Verify content, editability, structure, template geometry, and media")
    validate_parser.add_argument("--template", required=True)
    validate_parser.add_argument("--content", required=True)
    validate_parser.add_argument("--pptx", required=True)
    for command in [bootstrap_parser, build_parser, validate_parser]:
        command.add_argument("--profile", required=True)
    for command in [bootstrap_parser, build_parser]:
        command.add_argument("--output", required=True)
        command.add_argument("--force", action="store_true", help="Explicitly replace an existing generated output")
    args = parser.parse_args()
    try:
        result = {"bootstrap": bootstrap, "build": build, "validate": validate}[args.command](args)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (DeckError, OSError, KeyError, TypeError, ET.ParseError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        print(json.dumps({"status": "error", "error": str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
