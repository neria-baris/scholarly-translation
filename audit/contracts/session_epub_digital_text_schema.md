# Session EPUB-Schema — non-geometric digital-text source evidence

```yaml
task_id: session_epub_digital_text_schema
milestone: "Resolve the open EPUB-translation schema question (audit/current_state.md, 2026-10-05): extend the core schema with a new non-geometric digital-text origin type so EPUB input can satisfy translation.build_translation_request, instead of shipping PDF-only."
objective: >
  translation.build_translation_request transitively requires every source
  reading to carry literal provenance stage == "digital-pdf@1" plus positive
  pdf_width/pdf_height (enforced in source_reading.py validate_candidate,
  ~lines 131-162). EPUB text has no page geometry. The user has chosen to
  extend the schema rather than fabricate false provenance. This contract
  adds a new, non-geometric "digital-text" source-evidence origin to
  source_reading.py/document_structure.py so an EPUB Document can produce a
  valid schema-2 structure (readings/nodes/units) through the existing,
  unmodified build_readings -> build_structure_v2 pipeline. Because
  translation.py, context_strategy.py, review_qa.py, document_state.py and
  glossary.py already consume the generic schema-2 structure dict (not PDF
  fields directly, aside from the always-populated structure["pdf_hash"]
  passthrough field, which stays populated with document.input_hash for any
  source kind), none of those modules need to change: this is strictly a
  source_reading.py/document_structure.py/records.py schema extension plus a
  new scholarly_translation/epub_extract.py producer, mirroring pdf_extract.py.
in_scope:
  - records.py: additive, backward-compatible Segment dataclass fields
    (default None) carrying the block's already-known structural kind/level
    for non-geometric sources, e.g. node_kind/node_level. No change to
    existing PDF behavior or serialization defaults.
  - source_reading.py:
    - A new candidate origin "digital-text" (alongside existing "digital"
      and "ocr"), used only when document.source_kind == "epub". Its
      candidates carry pdf_width = pdf_height = None (explicit absence, never
      a fabricated geometry value) and a new provenance stage literal
      "digital-text-epub@1".
    - A new anchor shape for "digital-text" candidates: one anchor per
      logical block (kind == "block"), with segment_id/region_id as today's
      "digital" anchors but no bbox/pixel_bbox/image fields, plus the
      block's node_kind/node_level carried through from the Segment fields
      above. No pixel-to-PDF bbox mapping check applies to this origin.
    - build_readings: accept document.source_kind in ("pdf", "epub").
      "epub" documents build a single "digital-text" candidate per page
      (no OCR path — OCR remains PDF-only) and otherwise flow through the
      exact same decisions/previous_readings/versioning logic already
      implemented for "digital"/"ocr".
    - validate_candidate/validate_anchors branch on origin to apply the
      right shape; no relaxation of the existing "digital"/"ocr" PDF/OCR
      checks (bbox, pixel mapping, image evidence) is permitted.
  - document_structure.py:
    - _build_nodes_for_reading must branch on the resolved candidate's
      origin. For "digital-text", build nodes directly from the selected
      candidate's anchors (one node per anchor, using its node_kind/
      node_level) instead of re-deriving kind/level via classify_line/
      _classified_lines/_merge_paragraph_lines. This is required: EPUB
      already encodes its own block structure unambiguously in XHTML markup
      (see export_epub.py's existing module docstring reasoning,
      scholarly_translation/export_epub.py lines 1-24); re-deriving
      heading/paragraph/list kind from flattened plain text via regex
      heuristics would be exactly the "second independent interpretation of
      chapters/headings" the project contract forbids.
    - Validate node_kind against the existing NODE_KINDS vocabulary at this
      point (document_structure.py owns that vocabulary); raise
      StructureError on an unrecognized kind rather than guessing.
    - For "digital"/"ocr" origins, _build_nodes_for_reading's existing
      heuristic path is unchanged.
    - Everything downstream of nodes (unit grouping via
      _group_spans_from_nodes, unit-node links, continuity checks, revision
      history/versioning, validate_structure_v2) already operates generically
      on node/unit dicts and must keep working unchanged for both origins.
  - A new scholarly_translation/epub_extract.py, mirroring pdf_extract.py's
    shape (extract_epub(path_or_bytes, language, document_version=1) ->
    Document, raising a local EpubExtractionError that never carries page
    content), producing one Page per EPUB spine chapter (page_number = spine
    order, width = height = None, source_text = the chapter's blocks joined
    the same way pdf_extract joins lines) and one Segment per discovered
    HTML block (h1-h6/p/li/blockquote), each carrying node_kind/node_level
    via a small, explicit tag -> (kind, level) table reusing document_
    structure.NODE_KINDS (e.g. h1 -> heading, h2..h6 -> subheading, p ->
    paragraph, li -> list, blockquote -> quotation; builder may refine
    within NODE_KINDS, but may not invent per-chapter "part/chapter/section"
    guesses that EPUB markup does not actually encode).
    document.input_hash = sha256 of the archive bytes; stage_id =
    "digital-text-epub", stage_version = 1; source_kind = "epub".
  - Must reuse, not duplicate, export_epub.py's existing defensive
    zipfile/XML archive-reading and block-discovery logic (DOCTYPE/ENTITY
    rejection, encrypted-content rejection, out-of-archive/out-of-bounds
    reference rejection, XHTML media-type checks). Factor the shared
    primitives into a small shared helper (or a shared private module) that
    both export_epub.py and epub_extract.py import, rather than copying the
    parsing code.
  - tests/test_source_reading.py (or equivalent) and a new
    tests/test_epub_extract.py: the "digital-text" candidate/anchor shape,
    build_readings for an EPUB document, document_structure.build_structure
    producing valid nodes/units/unit_node_links from an EPUB Document end to
    end, and build_translation_request successfully building a
    TranslationRequest for an EPUB-derived unit (reusing the existing mock
    provider) — this last check is the actual acceptance proof that the
    original blocking error is resolved.
out_of_scope:
  - Changing translation.py, context_strategy.py, review_qa.py,
    document_state.py or glossary.py. If any of them turns out to need an
    actual code change (not just passing today), stop and report that as a
    deviation rather than guessing — per the objective above, the design
    expectation is that none of them do.
  - Reconciling export_epub.py's existing bespoke epub-structure@1
    extraction/export path with this new schema-2-capable EPUB structure.
    export_epub.py's export_epub()/extract_epub_structure() stay as they are
    for this contract; wiring translated schema-2 EPUB units back into a
    rebuilt EPUB file, and retiring/adapting extract_epub_structure's now-
    redundant structure production, is explicitly left to Session G's
    cross-component review (audit/claude_integration_conductor.md section 2
    already lists "document structure and PDF/EPUB export" and "exporter and
    UI download behavior" as things G must check).
  - Wiring epub_extract.py into document_draft.py/web_ui.py's simple UI job
    runner (DocumentJobs currently explicitly refuses EPUB uploads). That is
    UI/job-runner integration work, not schema work; leave the explicit
    refusal in place and leave it for Session G or a small following F-style
    session.
  - OCR for EPUB (EPUB text is already digital; there is no scanned-image
    case to support).
  - Any PDF-path behavior change. The full existing PDF test suite must pass
    unchanged.
relevant_paths:
  - scholarly_translation/source_reading.py
  - scholarly_translation/document_structure.py
  - scholarly_translation/records.py
  - scholarly_translation/segmentation.py (legacy schema-1 path; reference
    only — do not add EPUB support to the legacy schema-1 line model)
  - scholarly_translation/pdf_extract.py (reference: the Document/Page
    construction pattern to mirror for epub_extract.py)
  - scholarly_translation/export_epub.py (reference + refactor target for
    the shared archive-parsing helper; do not change its export behavior)
  - scholarly_translation/translation.py (reference only — prove it needs no
    change)
  - audit/current_state.md (the open question this contract resolves)
interface_contract: >
  epub_extract.extract_epub(path_or_bytes, language, document_version=1)
  returns a schema-3 Document with source_kind == "epub" that
  source_reading.build_readings and document_structure.build_structure
  accept without modification to their public signatures. The resulting
  structure dict is schema 2, indistinguishable in shape from a PDF-derived
  structure (same field set, same validate_structure_v2 rules), so
  translation.build_translation_request(structure, glossary, unit_id,
  profile_id, provider, model, ...) succeeds for an EPUB-derived unit_id
  exactly as it does today for a PDF-derived one.
acceptance_checks:
  - "python -B -m unittest discover -s tests" passes with no regression in
    the pre-session baseline test count (513 tests per audit/current_state.md
    at base commit 20fa0c9); new tests add to it.
  - A test builds a small synthetic EPUB fixture (reuse the construction
    pattern in tests/test_document_draft.py's or export_epub's EPUB test
    helpers), extracts it with epub_extract.extract_epub, resolves its one
    reading via build_readings with an explicit human decision, and confirms
    document_structure.build_structure produces nodes whose kind/level match
    the fixture's actual h1/p/li/blockquote tags (not a classify_line guess).
  - A test confirms a deliberately wrong node_kind in a candidate anchor is
    rejected by document_structure.py with StructureError, not silently
    accepted.
  - A test confirms the full existing PDF acceptance path (build_readings,
    build_structure, build_translation_request) is byte-for-byte unaffected:
    same candidate/anchor shapes, same errors, same hashes.
  - A test calls translation.build_translation_request with the EPUB-derived
    structure/unit/glossary/mock provider and gets back a valid
    TranslationRequest (the concrete proof the original blocking error -
    "every reading candidate must carry stage == digital-pdf@1 plus positive
    pdf_width/pdf_height" - no longer applies to EPUB input).
known_risks:
  - This is a genuine, cross-cutting schema change (source_reading.py and
    document_structure.py are both unusually strict, hash/shape-validated
    modules). Keep the change additive and branch-on-origin throughout;
    never relax an existing PDF/OCR check to accommodate EPUB.
  - Resist the temptation to reuse classify_line for EPUB "to keep it
    simple" - that would silently reintroduce the exact problem (a second,
    heuristic interpretation of structure) this contract exists to avoid.
  - Keep the tag -> (kind, level) mapping small and explicit; do not invent
    part/chapter/section guessing for EPUB that its markup does not encode.
source_provenance_required: true
builder_model: "Claude Sonnet 5 (sub-agent, isolated worktree)"
reason_for_model: "Scoped, well-specified schema-extension task within an existing contract; no demonstrated difficulty requiring Opus."
budgets:
  api_usd_hard: 0
  model_turns_hard: 0
  tool_calls_soft: 0
  wall_minutes_soft: 0
review_trigger: "Any change touching source_reading.py/document_structure.py/records.py validation logic, or any change to translation.py/context_strategy.py/review_qa.py/document_state.py/glossary.py (which should not be necessary - flag immediately if it turns out to be): conductor reviews full diff before merge into main."
stop_condition: >
  Ask the conductor/user only for a genuine product/architecture choice not
  already settled here (e.g. a different tag->kind mapping that changes
  user-visible EPUB chapter structure, or a real need to touch
  translation.py/context_strategy.py contrary to this contract's design
  expectation). Routine implementation decisions (exact module layout, exact
  shared-helper boundary between export_epub.py and epub_extract.py) do not
  require escalation.
```
