# Session F — Simple UI Integration

```yaml
task_id: session_f_simple_ui_integration
milestone: "F — Simple UI Integration"
objective: >
  Make the existing simple upload/translate/download UI
  (scholarly_translation/document_draft.py + web_ui.py + ui.html/ui.css/
  ui.js, the "put a PDF/EPUB in -> translate -> download" flow, NOT the
  separate advanced CLI-step dashboard reachable via gui.py's STEPS /
  web_ui.py's /run endpoint) actually drive the now-integrated canonical
  backend, per the full F specification in
  audit/claude_integration_conductor.md section "# F — Simple UI
  Integration". Read that section in full before starting.
context_discovered_by_conductor: >
  document_draft.py currently does NOT use the canonical pipeline at all:
  it does its own ad-hoc fixed-size (CHUNK_CHARS=1800) text chunking
  instead of document_structure/segmentation's semantic translation
  units, hard-codes exactly two OpenAI models in a local MODELS dict
  instead of model_config.py's provider-neutral registry, calls the
  openai SDK directly instead of model_adapter.build_translation_adapter,
  never calls review_qa.py (no quality-mode distinction exists today),
  and only ever renders plain HTML/TXT (render_download) instead of the
  new export_pdf.py/export_epub.py (Session X). This session's job is to
  replace those internals while PRESERVING DocumentJobs' valuable existing
  shape: one-active-job-at-a-time, durable job.json persistence, status
  polling, resumability after interruption, and local human-edit/review of
  a chunk's text. Do not rewrite that job-runner skeleton; rewire what it
  calls.
in_scope:
  - scholarly_translation/document_draft.py: replace internal extraction/
    translation/download with canonical-pipeline calls (see
    interface_contract). Keep job_id/status/resumability/locking/
    human-edit-with-revision-check behavior intact; existing tests in
    tests/test_document_draft.py that cover that job-runner shape must
    keep passing or be deliberately, visibly updated (never silently
    weakened) if a field's meaning changes.
  - scholarly_translation/web_ui.py: extend (do not replace) the existing
    /document-config, /document-translate, /document-job, /document-review,
    /document-download handlers for the new profile/model/quality-mode/
    output-format controls. Reuse the existing token/origin-guard pattern;
    do not add a new unguarded route.
  - scholarly_translation/ui.html, ui.css, ui.js: add Academic/Literary
    profile choice, a simple `Model: Auto | <configured models>` selector
    (advanced section may expose independent translator/semantic_reviewer/
    chapter_qa/candidate_evaluator/context_state_builder role pickers,
    per model_config.py's ROLES, but normal use requires none of them),
    Fast/Checked/Thorough quality-mode choice, and
    "Download translated PDF/EPUB" in place of the current HTML/TXT-only
    download. Preserve the existing simple visual direction; do not turn
    this into the advanced dashboard or add pipeline/Gate/cache
    terminology to the primary screen.
  - A small, explicitly-flagged adapter (see known_risks) to bridge
    export_epub.py's `epub-structure@1` (Session X, translatable blocks
    discovered from EPUB's own XHTML) into a structure the canonical
    translation.py path (build_translation_request_for_role, which calls
    segmentation.validate_structure) will accept, so EPUB and PDF both
    flow through the same translation/review code. Keep this adapter as
    small and additive as possible; do not change document_structure.py's
    schema-2 contract or export_epub.py's own behavior to accommodate it.
  - tests/test_document_draft.py and tests/test_web_ui.py updates/additions
    for all of the above.
out_of_scope:
  - OCR; scanned pages remain unsupported in this simple flow exactly as
    today (a page with no extractable text surfaces a clear error, same
    behavior/spirit as the current "OCR required" message).
  - Wiring Session C's chapter-QA output into Session D's
    document_state.py persistent-state store (propose_item/find_conflicts/
    commit_update) - that cross-chapter memory loop is explicitly Session
    G's job per the user's 2026-10-05 addendum
    (audit/raw/addendum_2026-10-05_persistent_state.md). This session may
    construct a fresh, empty `document_state.new_document_state(document_id)`
    per job and thread it through `build_translation_request_for_role`'s
    optional `document_state` parameter so later chapters see earlier
    ones' persisted decisions IF Session G has already populated it by
    the time this session runs - but this session must NOT itself call
    chapter QA to produce and commit state updates. If Session G has not
    yet run, passing an always-empty state (or omitting it, `None`) is
    correct and sufficient for this session's own acceptance checks.
  - The separate advanced CLI-step dashboard (gui.py STEPS, web_ui.py's
    `/run`/`/source-*`/`/glossary-*` endpoints) and its own UI panel in
    ui.html - leave these exactly as they are; this session only touches
    the simple document flow.
  - Redesigning translation, context, review, profile, or export logic
    themselves (Sessions B/C/D/X's own modules) beyond the smallest
    adapter above. A UI bug in export_pdf.py/export_epub.py found during
    this work should be reported, not silently patched around here,
    unless it is a one-line, obviously-safe fix - otherwise flag it for
    the conductor/Session G.
  - RAG, embeddings, a new frontend framework, a project-management
    dashboard, exposing every backend setting to the user.
relevant_paths:
  - scholarly_translation/document_draft.py
  - scholarly_translation/web_ui.py
  - scholarly_translation/ui.html
  - scholarly_translation/ui.css
  - scholarly_translation/ui.js
  - scholarly_translation/pdf_extract.py (extract_pdf -> schema-3 Document)
  - scholarly_translation/segmentation.py (build_structure -> schema-2
    document_structure; validate_structure)
  - scholarly_translation/export_epub.py (extract_epub_structure,
    SCHEMA="epub-structure@1" - read this module's own docstring in full,
    it explains exactly why EPUB has no canonical document_structure
    producer today)
  - scholarly_translation/translation.py
    (build_translation_request_for_role, run_translation,
    build_whole_chapter_translation_request)
  - scholarly_translation/translation_profiles.py (SUPPORTED_PROFILE_IDS:
    "scholarly"/"literary")
  - scholarly_translation/model_config.py (ModelConfiguration,
    load_model_configuration, ROLES, ModelCapabilities)
  - scholarly_translation/review_qa.py (UNIT_REVIEW_POLICIES
    off/risk_based/all, CHAPTER_QA_POLICIES off/on, RISK_FLAG_KEYS,
    build_chapter_qa_request_for_role, run_chapter_qa; unit-review
    equivalents earlier in the file)
  - scholarly_translation/export_pdf.py, export_common.py (export_pdf)
  - scholarly_translation/document_state.py (new_document_state only, for
    the pass-through described above)
  - scholarly_translation/model_adapter.py (build_translation_adapter,
    shared by translation.py/review_qa.py; use this instead of a raw
    openai.OpenAI() client call)
  - model_config.example.json (the config-file shape the UI's model list
    is populated from; a real deployment points `--model-config` or an
    equivalent UI-supplied path at a file shaped like this)
  - tests/test_document_draft.py, tests/test_web_ui.py
inputs_and_fixtures:
  - Small synthetic PDF/EPUB fixtures (reuse tests/pdf_fixture.py and the
    EPUB-construction helpers already used by tests/test_document_draft.py
    and tests/test_export_epub.py). No live provider calls; use the mock
    provider/adapter path throughout tests, exactly as every prior session
    has.
interface_contract: >
  For a PDF job: `pdf_extract.extract_pdf(path, language)` ->
  `segmentation.build_structure(document)` -> canonical schema-2
  `document_structure`. For an EPUB job: `export_epub.extract_epub_structure(path)`
  -> the new small adapter -> a document_structure translation.py will
  accept (document_id/page_id/reading_id/etc. may be synthesized
  deterministically from the EPUB's own chapter/element identity; this is
  bookkeeping, not scholarly interpretation). For each resulting
  translation unit, in document order: resolve the configured (or Auto
  default) translator role via `ModelConfiguration.resolve`/
  `build_translation_request_for_role` (so Session D's chapter-aware
  context and model-aware budget automatically activate whenever
  `ModelCapabilities` are configured) -> `run_translation`. Map the UI
  quality mode onto review_qa.py policies: Fast = unit review `off`,
  chapter QA `off`; Checked = unit review `risk_based` (driven by
  `run_translation`'s own findings/translation_note exactly as
  RISK_FLAG_KEYS describes) plus chapter QA `on` after a chapter's units
  are assembled; Thorough = unit review `all` plus chapter QA `on`. Map
  the UI profile choice directly onto `profile_id` ("scholarly"/
  "literary") with no UI-side prompt logic. After all units of the job are
  translated (and reviewed per the active quality mode), call
  `export_pdf.export_pdf`/`export_epub.export_epub` (input format decides
  which) with the resulting `unit_id -> {"text", "approved", "status"}`
  mapping, and surface the exporter's own `limitations` list to the user
  as a concise, readable warning (never silently claiming perfect
  preservation). "Auto" model selection, when no model-config file/role
  selections are supplied, must fall back to today's existing simple
  behavior (the existing `mock`/demo path, or a single configured default
  if one exists) rather than erroring - never silently picking an
  arbitrary paid provider. Progress reporting must use meaningful stages
  ("Reading document" / "Translating" / "Reviewing" / "Rebuilding
  document" / "Complete") and, where chapter-level nodes exist, "Chapter K
  of N"; never raw internal stage/Gate names.
acceptance_checks:
  - "python -B -m unittest discover -s tests" passes with no regression
    against this session's starting baseline (record exact before/after
    counts).
  - A test demonstrates a small synthetic digital-text PDF fixture flowing
    end-to-end: upload -> structure -> per-unit mock translation -> Fast
    mode (no review calls) -> export_pdf -> a valid PDF byte stream.
  - A test demonstrates the same for a small synthetic EPUB fixture,
    through the new adapter and export_epub, producing a valid rewritten
    EPUB.
  - A test demonstrates Checked mode triggers chapter QA after a chapter's
    units are assembled (using a deterministic fake generate callable, no
    network) and Thorough mode triggers unit review for every unit, while
    Fast mode calls no review adapter at all - mirroring Session C's own
    "skipped paths never call the adapter" invariant.
  - A test demonstrates Academic vs Literary profile selection reaches the
    actual `profile_id` used in the constructed translation request
    (not merely stored and ignored).
  - A test demonstrates the model list shown to the UI is populated from a
    supplied model-config file/registry, not a hard-coded list, and that
    "Auto" works with no model-config file supplied at all.
  - A test demonstrates a job surviving/resuming the same way the existing
    DocumentJobs interruption-detection test does today (do not regress
    this).
  - A test demonstrates the exporter's limitations list reaches the job
    record/UI-facing result rather than being discarded.
  - A test demonstrates that the advanced CLI-step dashboard's existing
    behavior (gui.py STEPS, `/run` and related endpoints) is unaffected.
known_risks:
  - The EPUB-structure adapter is this session's one genuinely new piece
    of integration surface (bridging export_epub.py's `epub-structure@1`
    and translation.py's expected document_structure). Keep it minimal:
    synthesize only the fields segmentation.validate_structure/
    translation.build_translation_request actually require, do not invent
    additional scholarly semantics (e.g. no fabricated page concept beyond
    "one EPUB chapter == one page_id" or similarly simple, clearly
    documented bookkeeping), and name it clearly as EPUB-specific
    (e.g. in export_epub.py itself or a small, obviously-scoped new
    function) so Session G's cross-component review can find and judge it
    easily.
  - Do not let "populate models from the registry" become a reason to
    call a live paid provider during tests or during this session's own
    verification; `mock`/fake adapters throughout, exactly as every prior
    session.
  - Keep budget/credential handling working for whichever provider is
    actually configured (not hard-coded to OpenAI as today); reuse
    model_adapter.build_translation_adapter's existing credential-missing
    error path rather than inventing a new one.
source_provenance_required: true
builder_model: "Claude Sonnet 5 (sub-agent, isolated worktree)"
reason_for_model: "Larger but still well-specified integration task; escalate to Opus only on demonstrated difficulty."
budgets:
  api_usd_hard: 0
  model_turns_hard: 0
  tool_calls_soft: 0
  wall_minutes_soft: 0
review_trigger: "Touches the public-facing UI/API surface and bridges two structure schemas: conductor reviews diff before merge into main."
stop_condition: >
  Ask the conductor/user only for a genuine product/architecture choice
  not already settled above - e.g. if the EPUB-structure adapter turns out
  to require a much larger reinterpretation than "smallest adapter" can
  reasonably cover, stop and report the exact blocker rather than
  improvising a second structure-schema redesign. Routine implementation
  decisions (exact endpoint field names, UI copy/layout within the
  existing visual direction) do not require escalation.
```
