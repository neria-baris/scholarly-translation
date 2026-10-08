# CJK-STRUCTURE: Japanese and mixed Japanese/Latin page structure

Date: 2026-10-07. Base: 6f70896. Claude continuity, user-directed. Branch `fix/cjk-structure`.
User report: the translated Japanese article (ronso_43_027.pdf) came out as short paragraphs, each
followed by a bold line; units were sentence fragments, so the translator repeated content
across neighbouring units. The user also asked for better handling of mixed English/Japanese text.

Root causes (measured on that article: 218 nodes, 66 false `heading`):
- `article_layout.analyze_readings` estimated the body type size from lines with >= 4 spaced
  words, which Japanese almost never has, so the estimate came from footnotes (9.73 vs 10.32 pt).
  A Japanese line that also holds digits, Latin letters or ASCII brackets has a ~1.10x taller
  box (11.31 pt), so it became a display-size `heading` (43 lines).
- `classify_line` used `isupper()`/`istitle()`, which ignore uncased characters: "形式体系A" and
  "Kurt Gödel" lines became `heading` (and the reference list ended at a line with "…I」").
- `_merge_paragraph_lines` broke at every line ending in 。, but Japanese wraps at any character.

Owns: `document_structure.py` (line classification, paragraph merging),
`article_layout.py` (layout overrides, note labels/marks), one prompt rule in
`chapter_pipeline.py` (mirrored in `tests/_chapter_pipeline_reference.py`).

Behaviour:
- Body size: lines with >= 4 words or >= 10 Japanese characters; heights of mixed-script lines
  are divided by `MIXED_SCRIPT_HEIGHT` (1.10) everywhere a height is compared (body, note zone,
  display heading).
- Japanese display headings are at most 40 characters, do not end in Japanese clause punctuation
  and are narrower than 85% of the page's body-line width.
- `classify_line`: case rules only for lines without Japanese; Japanese "N. title" (one or two
  digit section number, never a year or count) and standalone section words (序論, 結論, ...)
  are `subsection` 4.
- Paragraph merging with page geometry (digital/OCR readings): a break at an indented next line
  or a gap wider than the page's normal line gap; a Japanese full-width line ending in 。 continues
  the paragraph. A line overlapping the line above (emphasis dots, a subscript) stays inside the
  paragraph and never decides a break; a lone number overlapping the line above is no longer
  `page_furniture`. Without geometry the previous text-only rule is unchanged.
- Endnotes: after a standalone notes heading (註, 注, Notes, ...) labelled lines are `note`
  nodes, until the references heading or a display heading; aborted if the first line has no
  label. Labels accept (1) and （1）. Bracketed marks right after Japanese text, "…である(8)。",
  are note marks spanning their brackets (page-local linking as before).
- References: Japanese headings (文献, 参考文献, 引用文献, ...), entries starting with ―――, a
  name particle (van, de, ...) or "著者 (1995)"; the list may reclaim lines the note zone took.
- Translation prompt (batches of more than one unit): a unit may begin or end mid-sentence at a
  page break; translate only its own words, never repeat or complete a neighbour's.

Acceptance: `tests/test_cjk_structure.py` (9 tests; 7 fail on the base). Full suite 1325 OK.
Real article: 218 → 115 nodes, false headings 66 → 0 (5 real headings, 5 section headings,
13 endnotes, 25 reference entries). Gate-10 sources rebuilt old/new: ja_epistemology 32 → 5
headings, ja_books 16 → 3; French: new breaks are real (block quotes, licence paragraph);
English single-column logic paper: 9 "BF₁₀" subscripts kept in the text instead of being dropped
as page furniture. Two-column PDFs whose extraction interleaves columns stay unusable, as before.

Out of scope: reasoning effort (user handles separately); endnote marks linked across pages;
two-column reading order; terminology controls (separate change).
