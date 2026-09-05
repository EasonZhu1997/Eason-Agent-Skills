# Prompt recipes

Use these as scaffolding, not as a source of invented nodes.

## Common header

```text
Use case: infographic-diagram
Asset type: hand-drawn paper relationship diagram
Reference policy: If a user-authorized image is supplied, it is a STYLE REFERENCE ONLY; do not copy its subject matter or text. With no reference image, use only the written style specification below and omit image-reference parameters.
Scene: warm off-white textured paper photographed top-down on a dark charcoal desk.
Style: imperfect black gel-pen doodles and cross-hatching, royal-blue handwritten labels and arrows, sparse mustard-yellow highlights.
People and devices: modern people and contemporary devices for technical diagrams, unless the user explicitly specifies a different setting.
Constraints: exact quoted labels, generous whitespace, visible paper margins, no logos, no watermark, no extra text, no polished vector look.
```

## Technical architecture

```text
Primary request: Draw an accurate architecture relationship diagram for "<TITLE>".
Composition: <portrait or landscape>; inputs at the top/left, independent components clearly separated, shared rules underneath, runtime/output chain below, governance or evidence branch kept separate.
Required nodes and text (verbatim):
- "<NODE 1>"
- "<NODE 2>"
- "<NODE 3>"
Required arrows:
- "<NODE 1>" → "<NODE 2>" labeled "<RELATION>"
Boundaries:
- "<A>" and "<B>" are independent; do not merge them.
- "<X>" is a separate branch and does not imply "<Y>".
```

## Workflow

```text
Primary request: Draw a step-by-step workflow titled "<TITLE>".
Composition: top-to-bottom paper poster with large numbered stages, one main route and clearly detached exception/approval branches.
Stages (verbatim): "<1>" → "<2>" → "<3>" → "<4>".
Decision/exception: from "<STAGE>" branch to "<OUTCOME>" with a dotted blue arrow.
Final principle: "<SHORT RULE>".
```

## Relationship map

```text
Primary request: Draw a relationship map titled "<TITLE>".
Composition: central hand-drawn ledger or scroll for "<HUB>", surrounding independent actors, labeled arrows showing what each sends or receives.
Actors (verbatim): "<A>", "<B>", "<C>".
Do not imply ownership, sequence, or data sharing unless explicitly listed.
```

## Timeline

```text
Primary request: Draw a chronological relationship timeline titled "<TITLE>".
Composition: major illustrated moments above a blue handwritten horizontal date line; arrows connect causes, handoffs, and outcomes.
Dates/milestones (verbatim): "<DATE 1>", "<DATE 2>", "<DATE 3>".
Use black doodles for events, blue ink for dates and relationships, and one yellow accent for the pivotal event.
```

## Final fidelity block

Append this to every final prompt:

```text
Render every quoted label verbatim with correct Chinese and English acronyms. Use large legible handwriting and no tiny paragraphs. Keep all objects and text safely inside the paper. Preserve every stated arrow direction and independence boundary. No copied subject matter from the style reference, no extra labels, no logo, no watermark.
```
