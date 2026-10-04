# Session X — PDF/EPUB Reconstruction and Export

```yaml
task_id: session_x_export
milestone: "X — PDF/EPUB Reconstruction and Export"
objective: >
  Implement format-preserving translated-document export operating on the
  canonical document_structure (schema 2) nodes: PDF input -> translated PDF
  output, EPUB input -> translated EPUB output, per the full X specification
  in audit/claude_integration_conductor.md (sections 1-9). This is a new
  canonical export path, distinct from and not replacing the existing
  non-canonical demo flow in document_draft.py/web_ui.py (schema
  document-draft@1, approved always false, HTML/TXT only).
in_scope:
  - A new module or small package, e.g. scholarly_translation/export_pdf.py
    and scholarly_translation/export_epub.py (or scholarly_translation/export/).
  - Reuse existing dependencies first: reportlab (already a pinned dependency,
    used for PDF generation) and the zipfile+lxml approach document_draft.py
    already uses for EPUB spine reading (lxml is already installed). Adding
    a focused EPUB-writing dependency (e.g. ebooklib) is acceptable only if
    justified in the delivery package (license check, why zipfile+lxml alone
    is insufficient) and recorded in requirements.txt.
  - tests/test_export_pdf.py, tests/test_export_epub.py with small
    deterministic fixtures (reuse tests/pdf_fixture.py conventions).
out_of_scope:
  - Changing translation, context (Session D), semantic review, or
    model/provider selection (Session E) logic.
  - document_draft.py's existing demo upload/translate/download flow and its
    HTML/TXT output (read-only reference; do not modify its behavior or
    schema).
  - UI work (Session F). This session only needs to produce a callable
    export function; wiring it into web_ui.py/ui.html is Session F's job.
  - OCR; pixel-perfect PDF reproduction; a desktop-publishing suite.
relevant_paths:
  - scholarly_translation/document_structure.py
  - scholarly_translation/STRUCTURE_SCHEMA.md
  - scholarly_translation/segmentation.py
  - scholarly_translation/pdf_extract.py (reference only: original page
    geometry/hash fields available on the source Document)
  - scholarly_translation/document_draft.py (reference only: existing
    zipfile+lxml EPUB spine-reading pattern and its safety checks, e.g.
    rejecting unsupported XML structure / out-of-bounds links / encrypted
    archives - reuse the same defensive parsing approach, do not weaken it)
  - requirements.txt
  - tests/pdf_fixture.py
inputs_and_fixtures:
  - Small synthetic PDF/EPUB fixtures built the same way existing tests do
    (tests/pdf_fixture.py, tests/test_document_draft.py's EPUB construction
    helpers may be read for the construction pattern). No real scholarly
    PDFs required for this session.
interface_contract: >
  Export functions take the canonical document_structure (nodes + units)
  plus a mapping of unit_id -> translated text (and per-unit
  provenance/approval state) and produce: (a) for EPUB input, a rebuilt
  EPUB preserving package metadata, spine order, TOC, chapter/HTML file
  structure, CSS, images and internal/external links, with translated text
  substituted into the existing HTML block structure and RTL/Hebrew
  document semantics added; (b) for PDF input, a reconstructed PDF using
  node kind/level/order (title/heading/body/note hierarchy, paragraphs,
  lists, block quotes, footnotes, captions, images, tables, formulas where
  representable) with RTL Hebrew text laid out correctly (correct
  bidi/punctuation, no mirrored characters, intact numbered lists), reflowing
  text rather than forcing it into original fixed boxes. Each output block
  must remain traceable to its source unit_id/node_id(s). When a structural
  element cannot be preserved, record it in an explicit, returned
  limitations list rather than silently dropping or mis-rendering it; never
  claim exact layout preservation when reflow occurred. Input format
  determines default output format (PDF->PDF, EPUB->EPUB); existing
  bilingual HTML/debug exports, if touched at all, remain secondary and
  unaffected.
acceptance_checks:
  - "python -B -m unittest discover -s tests" passes with no regression in
    the pre-session baseline test count; new export tests add to it.
  - EPUB: generated package passes a structural/validity check (well-formed
    OPF/NCX or nav, spine resolves, referenced files exist in the archive).
  - EPUB: chapter structure, TOC, CSS retention, images, internal/external
    links and Hebrew RTL output are each covered by a test.
  - PDF: heading hierarchy, paragraphs, footnotes, images, at least one
    simple table/formula case where supported, Hebrew RTL, multi-page
    generation and readable reflow are each covered by a test.
  - A test shows input format determines default output format.
  - A test shows source/translation structural linkage (unit_id/node_id)
    survives export and can be queried from the output or an accompanying
    manifest.
  - A test shows export failure (e.g. missing/invalid structure) is reported
    clearly via a specific exception, not a raw traceback leaking internals.
  - A test shows graceful degradation: a deliberately unsupported structural
    element (e.g. an irregular floating figure) produces a readable output
    plus a recorded limitation, not a silent drop or a crash.
known_risks:
  - EPUB and PDF reconstruction are both nontrivial; keep the first
    implementation to the smallest robust exporter that passes the
    acceptance checks above, per the stage prompt's explicit instruction to
    avoid pixel-perfect ambitions.
  - Must not build a second independent chapter/heading interpretation;
    always resolve hierarchy from document_structure nodes.
source_provenance_required: true
builder_model: "Claude Sonnet 5 (sub-agent, isolated worktree)"
reason_for_model: "Scoped, well-specified implementation task within an existing contract; no demonstrated difficulty requiring Opus."
budgets:
  api_usd_hard: 0
  model_turns_hard: 0
  tool_calls_soft: 0
  wall_minutes_soft: 0
review_trigger: "New runtime dependency, or any change touching document_structure/segmentation: conductor reviews diff before merge into main."
stop_condition: >
  Ask the conductor/user only for a genuine product/architecture choice,
  e.g. whether to add a new EPUB-writing dependency beyond zipfile+lxml.
  Routine implementation decisions (exact module layout, PDF layout
  parameters) do not require escalation.
```
