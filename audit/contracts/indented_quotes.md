# INDENTED-QUOTES contract

User request 2026-10-08 (follow-up to PDF-TYPOGRAPHY): block quotations that the source sets off by
indentation (no quote marks) were classified as `paragraph`, so no export could indent them.
Base: `feat/user-terms` (ea45a4b, includes CJK-STRUCTURE geometry). Branch `feat/quote-indent`.

- component: PDF/OCR page structure — `document_structure.py` (paragraph merging and a quotation pass).
- owns: `_page_layout` body edge (`left`) and merged-column flag, `_mark_indented_quotations`, the
  quote-end and in-quote sentence-end rules of `_continues_paragraph`.
- input: unchanged — a resolved digital/OCR reading with line anchors; EPUB (`digital-text`) untouched.
- output: unchanged schema; some `paragraph` nodes become `quotation` (an existing node kind that
  every exporter and the translation pipeline already handle).
- invariants:
  - body edge = leftmost line start shared by >= 3 wide lines and >= 15% of them (margin headers/footers ignored);
  - a quotation is a paragraph group whose lines all start >= 1.5 line heights inside the body edge at one
    shared edge (first line may sit further in); >= 3 lines, or smaller type; a 2-line block also when set off by
    extra space, next to another block at the same edge, or opening/closing the page's text (page-break continuation);
  - never a quotation: lines after a list item or reference entry (hanging indent), centered lines, a column edge
    (substantial lines end left of it), lines beside a drop capital or margin object, any block on a page whose
    extracted lines join two Japanese columns;
  - inside a quotation a full-width line ending a sentence continues it; a line further out ends it.
- errors / side_effects: none; no provider calls. Node ids include kind, so retyped nodes get new ids on the next
  structure build (existing saved jobs keep their stored structure).
- acceptance: `tests/test_indented_quotes.py` (12), existing structure tests; real-source check: Japanese article
  9/9 quotations incl. 2 page-break continuations; French philosophy 6, French math education 2 (all real,
  with citations); English two-column/sidebar articles and Japanese two-column articles 0 false positives; one
  indented English abstract block (ja_books) marked as quotation, faithful to its layout.
- out_of_scope: right-to-left source pages (indent measured on the left); splitting joined columns in extraction;
  quotations only one line long; re-segmenting already translated jobs.
