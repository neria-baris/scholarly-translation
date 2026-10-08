# PDF-TYPOGRAPHY contract

User request 2026-10-08: Hebrew PDF output looks poor; quotations are not indented; no justified (flush both edges) text.

- component: translated PDF rendering (`export_pdf.py`) and its shared bidi/glyph helpers (`export_common.py`).
- owns: line layout (justification, indents, paragraph gaps, page splitting), edge-punctuation bidi rule, display stand-ins for undrawable punctuation.
- input: unchanged — schema-2 `document_structure`, `unit_id -> translation` mapping, optional `font_id`.
- output: unchanged `PdfExportResult` (content/manifest/limitations/page_count/font_id); only the drawn page changes.
- invariants:
  - paragraph, quotation, list, note and footnote lines are justified to the measure, except the last line of each paragraph and lines whose gaps would exceed 4 spaces;
  - each `\n` inside a unit is a paragraph break: its line is not justified and the next paragraph starts after a style gap (not at the top of a page);
  - quotations: 10pt, indented 30pt on both sides, for right-to-left and left-to-right blocks alike; list indent applies on the start side in either direction;
  - punctuation at the edges of a left-to-right island in a right-to-left line takes the paragraph direction (UAX #9 neutrals rule), without splitting bracket pairs and keeping `%`/`#` with numbers; letters, digits and inner punctuation of the island keep their order; a line without Hebrew inside a right-to-left block follows the block direction;
  - CJK brackets/fullwidth punctuation that no available font can draw are shown with a close stand-in, never an empty box;
  - blocks longer than 4 lines may split across pages with at least 2 lines at the bottom, avoiding a single last line at the top of the next page; headings reserve room for two following body lines;
  - drawn space glyphs keep copied text word-separated.
- errors / side_effects: none new; no provider calls, no persistent format change.
- acceptance: `tests/test_pdf_typography.py`; existing PDF/notes/math/font tests pass; full offline suite passes; rendered real job inspected visually.
- out_of_scope: detecting block quotations in source PDFs by indentation or type size (structure detection currently marks only lines wrapped in quote marks as `quotation`); CJK ideograph glyphs (no bundled CJK font); hyphenation; full UAX #9 (bidi stays line-level and token-based); HTML/EPUB export.
- changed expectation: a list marker `1.` in Hebrew now draws its period left of the number (as browsers show it); the earlier test asserting the opposite was revised.
