---
name: blue-ink-paper-diagram
description: Create accurate hand-drawn paper infographics using black ink doodles, blue handwritten labels and arrows, and sparse yellow accents. Use when the user asks for “蓝墨纸绘”, a hand-drawn technical architecture, workflow, relationship map, evidence chain, timeline, system diagram, or a visual matching the warm-paper black-pen blue-ink style.
---

# 蓝墨纸绘

Turn verified project or product relationships into a friendly photographed-paper infographic. Preserve technical truth first; apply the visual style second.

## Required resources

- Read [references/style-spec.md](references/style-spec.md) before generating.
- Read [references/prompt-recipes.md](references/prompt-recipes.md) when selecting a layout or composing the final prompt.
- This public package deliberately contains no third-party reference image. Without a user reference, generate from the written style specification and prompt recipes; do not ask for an image unnecessarily or rely on a private local file.
- When the user provides a reference they have permission to use, treat it as style-only input: never copy its people, names, dates, map, flag, or historical content unless explicitly requested and appropriate.

## Workflow

### 1. Establish the content contract

Inspect the source repository, document, or user-provided facts before drawing. Extract:

1. five to nine core nodes;
2. directed relationships and short arrow labels;
3. parallel, independent, shared, optional, and blocked relationships;
4. current-state boundaries versus future plans;
5. exact in-image labels, copied verbatim.

Do not infer that components are merged, deployed, published, or verified merely because they are related. Separate implementation, runtime, evidence, governance, and external publication when those states differ.

If architecture remains ambiguous after inspecting the available source, ask one focused question. Otherwise proceed with an explicit reasonable assumption.

### 2. Select the diagram structure

Choose the smallest structure that explains the relationship:

- layered architecture: inputs → independent products → shared rules → runtime/output;
- workflow: ordered stages with decision or evidence branches;
- relationship map: a central hub with independent surrounding actors;
- timeline: dated milestones with causes, handoffs, and outcomes;
- evidence diagram: implementation stages aligned with separately named proof levels.

Default to portrait when the story is primarily top-to-bottom or should resemble a sheet of paper. Use landscape for wide system layers or slide use.

### 3. Simplify before generation

- Keep visible labels to about 25 or fewer.
- Prefer two- to eight-word labels over paragraphs.
- Put detailed explanation outside the image.
- Use `≠`, locks, dotted arrows, braces, and small notes for boundaries.
- Never merge two distinct chains merely to make the composition symmetrical.
- Keep every acronym, version, protocol, and product name exact.

### 4. Generate with the built-in image tool

Use the built-in `image_gen` tool by default. With no reference, generate from the written specification and omit image-reference parameters. If the user provides an authorized reference, pass it as style input, never as an edit target unless the user explicitly requests an edit. Follow the current host's actual image tool instructions; if image generation is unavailable, return a ready-to-use prompt and clearly state that no image was generated.

Construct the prompt from [references/prompt-recipes.md](references/prompt-recipes.md). Quote every required label and state:

- any supplied reference image is for style only;
- the exact architecture and arrow directions;
- the required orientation and paper margins;
- all forbidden copied content and extra labels;
- no logo, watermark, cropped content, or polished vector look.

### 5. Inspect the rendered result

View the generated image at original detail and check:

- every required node is present;
- every arrow points in the correct direction;
- independent components still look independent;
- branches do not imply false sequencing;
- all Chinese text and English acronyms are legible and correctly spelled;
- no reference-image subject matter leaked into the new content;
- no content touches or crosses the paper edge;
- the result looks hand-drawn rather than digitally typeset.

Do not deliver a diagram with misspelled core labels or materially wrong relationships. Retry with one targeted correction. If dense exact text remains unstable after two focused retries, reduce the number of labels or ask whether a deterministic text-overlay version is acceptable.

### 6. Save and report

For a project-bound image, copy the selected output into a descriptive workspace path such as:

```text
assets/architecture/<subject>-handdrawn.png
```

Do not overwrite an existing asset; add a version suffix. Do not commit, push, upload, publish, or modify consuming documents unless the user requests it.

Report:

- the final image inline;
- the absolute saved path;
- dimensions and format;
- the final prompt or a compact faithful prompt specification;
- which image-generation tool was actually used, or that only a prompt was prepared;
- any unresolved text or architecture caveat.

## Invocation examples

```text
$blue-ink-paper-diagram 把这个仓库的技术架构画成一张手绘关系图
$blue-ink-paper-diagram 把这套发布流程画成白纸蓝墨风的步骤图
$blue-ink-paper-diagram 用同一画风画产品、用户和数据之间的关系
$blue-ink-paper-diagram 把这些里程碑画成一张手绘时间线
```
