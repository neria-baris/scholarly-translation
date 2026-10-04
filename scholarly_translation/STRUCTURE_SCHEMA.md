# Document structure schema: logical nodes and semantic units

Produced by `scholarly_translation.segmentation.build_structure` /
`document_structure.build_structure_v2`. Validated by
`scholarly_translation.segmentation.validate_structure`, which accepts either
schema below and never silently reinterprets one as the other.

## Schema 1 (`structure@1`, legacy, read-only going forward)

- Segmentation is one visual PDF/OCR line per translation unit
  (`_default_line_spans`), unless manual `boundaries` are supplied.
- Persisted fields: `schema_version` (1), `stage`, `document_id`,
  `document_version`, `pdf_hash`, `source_uri`, `language`, `input_hash`,
  `revision`, `readings`, `units`, `continuity`, `history`.
- `build_structure` no longer *produces* schema 1. Existing schema-1
  artifacts remain fully loadable and validated (`validate_structure`
  dispatches on `schema_version`), and remain usable as a `previous=`
  argument to `build_structure` (see "Crossing the schema boundary" below).
  `scholarly_translation.segmentation._build_structure_v1` still contains the
  legacy builder, for tests and historical-artifact reconstruction only.

## Schema 2 (`structure@2`, current default)

`build_structure` always builds schema 2 now. Two collections sit side by
side on top of the same resolved `readings`:

- **`nodes`**: conservative logical blocks reconstructed from visual lines.
  Each node has `node_id`, `node_version`, `kind`, `level`, document-wide
  `order`, `parent_node_id`, `reading_id`,
  `reading_version`, `document_id`, `page_id`, `language`,
  `source_char_start`/`source_char_end` (exact half-open span into the
  resolved reading text), `text` (always `reading.text[start:end]`,
    character-for-character), `anchors` (intersecting PDF/OCR anchors), and
    `predecessor_node_ids`.
  - `parent_node_id` is the nearest preceding structural node at a shallower
    level and may cross page boundaries; top-level nodes use `null`. `order`
    is contiguous document reading order. Part/chapter/section/subsection/
    heading/subheading map to levels 1–6; body nodes inherit the deepest
    active structural parent without fabricating a level of their own.
  - `kind` is one of: `part`, `chapter`, `section`, `subsection`, `heading`,
    `subheading`, `paragraph`, `scene_break`, `quotation`, `list`, `note`,
    `caption`, `formula`, `bibliography_entry`, `page_furniture`,
    `unsupported`. Classification (`classify_line`) is explicit regex-based
    heuristics over one visual line; anything that does not match a specific
    pattern is a plain `paragraph`, never a fabricated structural guess.
  - Consecutive `paragraph` lines merge into one paragraph node only when
    the earlier line does **not** end with sentence-final punctuation and
    the next line is textually adjacent (no intervening blank line) — this
    reconstructs PDF soft-wraps without ever rewriting or reflowing source
    characters (the merged `text` includes the original internal `\n`).
    Every other kind stays exactly one visual line per node.
- **`units`** (translation units; the exact schema-1 field shape:
  `unit_id`, `unit_version`, `reading_id`, `reading_version`,
  `reading_text_hash`, `document_id`, `page_id`, `language`,
  `source_char_start`, `source_char_end`, `text`, `anchors`, `status`,
  `warnings` and `predecessor_unit_ids`) so every existing direct consumer
  (`translation.py`, `glossary.py`, `human_review.py`,
  `translation_memory.py`, `ui_decisions.py`) keeps working unchanged.
  Units are formed by grouping adjacent `paragraph` nodes toward a
  ~2000-source-word default ceiling (`unit_policy={"max_unit_words": N}`
  narrows this; it is a word-count knob only, never a profile/route
  selector). Any non-paragraph node (heading, note, scene break, list,
  quotation, caption, formula, bibliography entry, page furniture) is
  always its own unit boundary — structural boundaries are preferred over
  the word-count heuristic. A group (or a single node) that still exceeds
  the ceiling is split at the strongest available internal boundary
  (a sentence break), never mid-sentence or mid-word; if no internal
  boundary exists the oversized span is kept whole.
  The deterministic size heuristic counts whitespace-delimited tokens for
  spaced text and individual Japanese/CJK characters conservatively; it is a
  bound, not a linguistic Japanese word segmenter. Sentence splitting accepts
  both Latin `.?!` and Japanese `。！？` terminators.
- **`unit_node_links`** provides one explicit record per unit with `unit_id`
  and the ordered, nonempty `node_ids` whose exact source spans intersect it.
  Keeping this mapping separate preserves the historical unit shape consumed
  by glossary, translation memory, translation, review and export artifacts.
- Top-level `unit_policy` persists the effective policy version and exact
  `max_unit_words`, so a later consumer can reproduce or invalidate the
  semantic-unit plan rather than inferring defaults from current code.
- A new top-level `legacy_predecessor_hash` field (sha256 hex or `null`)
  records that this document had a pre-existing schema-1 structure at the
  moment schema 2 started, without fabricating node/unit-level predecessor
  links into that legacy line model (see below).
- Explicit manual `boundaries` (unchanged shape: `{page_id: [[start,end],...]}`)
  still override the default grouping for a page's **units** exactly as in
  schema 1; they are validated the same way (exact, non-overlapping,
  in-bounds) and invalid plans still fail rather than being repaired.
  `nodes` are always built from the default classifier regardless of manual
  unit boundaries — nodes describe source structure, not a chosen
  translation-unit plan.

### Crossing the schema boundary

`build_structure(..., previous=<schema-1 artifact>)` is accepted. The
schema-1 artifact is fully re-validated (`_validate_structure_v1`), its
fingerprint is recorded as `legacy_predecessor_hash`, and a **fresh** schema-2
lineage starts (`revision.number == 1`, `revision.parent_revision is None`,
`history == []`, every node/unit `predecessor_*_ids == []`). Line-model units
are never reinterpreted as paragraph/heading nodes, and no fake continuity is
invented across the schema boundary — this is the "accepted without
fabricating new provenance" requirement.

## Known limitations (conservative by design)

- Classification is single-visual-line heuristics; multi-line headings,
  multi-line notes/captions, and footnotes that themselves wrap across
  lines are not reconstructed — each remaining line stays its own node.
- Page-furniture detection only recognizes bare/`"page"`-prefixed numeric
  lines; repeated running headers/footers are not detected or deduplicated
  across pages.
- The oversized-group splitter only cuts at `.?!。！？` sentence boundaries;
  a single run-on oversized sentence with no internal sentence boundary is
  kept whole rather than ever being cut mid-sentence.
- `unit_policy` only narrows the word-count ceiling; there is no literary
  vs. scholarly profile switch here (that remains out of scope for this
  module).
