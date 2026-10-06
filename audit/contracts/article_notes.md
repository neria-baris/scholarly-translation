# ARTICLE-NOTES — footnotes, reference lists, page furniture and mathematics in PDF articles

Date: 2026-10-06. Base: ea5cbeb (main). Branch feat/article-notes, worktree
.claude/worktrees/article-notes. Claude continuity, user-directed; built by Claude in one
worktree (no parallel builders: the change crosses structure, pipeline and export).

User decisions (2026-10-06): notes go to the bottom of the page as in the original (PDF);
the reference list stays in its original language; input is digital or scanned PDF; take
the mathematics into account.

Evidence (offline): `1 See Smith (2019), p. 4.` classifies as paragraph; only `[3] ...`
lines are notes; wrapped notes stay separate lines; a mark `earlier.12 The` is plain text;
running headers repeat on every page; bibliography entries must come back with Hebrew;
export_pdf renders notes inline (`footnotes_rendered_inline`).

## A. Source layout (new `article_layout.py`, `document_structure.py`)
No schema change: only node kinds and node spans change for NEW structures.
- Line geometry from the selected candidate's anchors: digital `line` anchors (bbox) or OCR
  `word` anchors (pdf_bbox, grouped by text line). Lines without geometry are left alone.
- Document pass over resolved readings before nodes are built:
  - body line height = median height of lines with >= 4 words (document-wide);
  - note zone: the trailing run of lines at the bottom of a page whose height <= 0.88 x body
    height, starting at a line that begins with a note label (1-3 digits, or * † ‡ §) and is
    below every body line; lines of the zone after a label line belong to that note; zone
    lines before the first label (top of zone) continue the previous page's last note;
  - page furniture: a first or last line of a page whose digit-normalised text repeats on at
    least 3 pages (or on every page of a 2-page document);
  - references: a short line that is exactly a references heading (References, Bibliography,
    Works Cited, Literature, Literatur, Bibliographie, Références, Riferimenti bibliografici,
    参考文献, Sources) becomes `heading`; following non-heading, non-note lines until the next
    heading become `bibliography_entry`, an entry continuing until a line ending in `.` is
    followed by a line that starts a new entry (author pattern, `[n]` or `n.`); the section
    ends at a heading-like line or a page whose lines are body-sized prose;
  - `Abstract` / `Keywords:`-style lines are kept (heading / paragraph).
- Overrides are applied in `_build_nodes_for_reading`; a multi-line note or entry is one
  node (contiguous span). EPUB (`digital-text`) structures are unchanged.

## B. Notes and marks (`article_layout.py`, pure, derived from the structure)
- `note_index(structure)` -> notes (unit id, label, page, continuation-of) and marks per
  unit. A mark is a digit run equal to a note label of the same page, glued to the end of a
  word of >= 2 letters or to closing punctuation (`. , ; : ! ? ) ” " ’`), followed by a space,
  punctuation or end; marks are taken in label order once each.
- Mathematics: never a mark when the run follows a single letter, a Greek letter, a math
  symbol, `^` or `_`, a digit, or sits in a `formula` node; equation numbers `(3)` are not
  glued and are never marks.
- Mark token in prompts and stored Hebrew: `[^12]`. `marked_text(structure, unit_id)`
  returns the unit text with the glued digits replaced by the token.

## C. Translation (`chapter_pipeline.py`)
- Passthrough units (no provider call, no review/QA): every node `page_furniture` or
  `bibliography_entry`, or a `formula` unit without translatable words. Their record holds
  the source text, `passthrough: <reason>`, review skipped. plan_chapter excludes them.
- Job records and translator/review/correction prompts use the marked text; the batch
  suffix explains `[^n]` (keep each exactly once, at the same place) and note units (keep
  the note number first) and that math, symbols and equation numbers are copied exactly.
- Parse: with marks in the source, the Hebrew keeps exactly the source's marks; a missing
  mark is appended at the end of the unit, an unknown or repeated one removed (format
  repair, finding `note_mark_relocated`); never a failed batch for a mark.

## D. Export
- PDF: every note unit with a label is a footnote: the body line that holds `[^n]` (drawn as
  a superscript number) and its note go on the same page; the notes sit at the page bottom
  under a short rule, smaller type, original numbers; a note too long for the rest of the
  page continues at the bottom of the next page. Unmatched notes are drawn where they were,
  with limitation `note_without_mark`. Text without Hebrew (references, formulas) is drawn
  left to right, left aligned (formulas centred). Page furniture omitted (as before).
- HTML: marks are `<sup><a>` links to a notes list at the end, with back links.
- Elsewhere (UI, other exports) `[^n]` shows as a superscript number.

## E. Tests
New tests for geometry, zone detection (digital and OCR shapes), furniture, references,
math exclusions, marks, passthrough planning/execution, parse repair, PDF footnote placement
(page of mark == page of note, continuation), HTML notes. Full offline suite. Paid calls 0.
