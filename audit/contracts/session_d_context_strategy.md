# Session D — Context Strategy

```yaml
task_id: session_d_context_strategy
milestone: "D — Context Strategy"
objective: >
  Replace the narrow previous/next-unit translation context in
  scholarly_translation/translation.py (build_context: target unit plus at
  most one previous/one next unit, each capped at MAX_NEIGHBOR_CHARS=2000)
  with a semantic-unit, chapter-aware context strategy, per the full D
  specification in audit/claude_integration_conductor.md (sections 1-11).
in_scope:
  - scholarly_translation/translation.py: build_context, build_translation_request,
    TranslationRequest fields, compute_cache_key, to_metadata_dict, run_translation
    plumbing needed to carry new context/provenance fields.
  - A new narrowly-scoped helper module if justified (e.g.
    scholarly_translation/context_strategy.py) for chapter-boundary lookup,
    context-layer assembly and model-aware budget sizing. Prefer extending
    translation.py over scattering logic across many new files.
  - Read-only consumption of scholarly_translation/document_structure.py and
    segmentation.py output (nodes, unit_node_links, unit_policy, kind/level/
    parent_node_id hierarchy already documented in STRUCTURE_SCHEMA.md) to
    locate the enclosing chapter/section for a unit and its node span.
    Adding small, additive read helpers there is acceptable; do not change
    the persisted node/unit schema version or existing field shapes.
  - scholarly_translation/model_config.py ModelCapabilities: read-only use of
    context_window/usable_context_tokens/max_output_tokens for budget sizing.
  - tests/test_translation.py and a new tests/test_context_strategy.py.
out_of_scope:
  - OCR (ocr.py), PDF/EPUB export (Session X), UI (Session F/web_ui.py/ui.html/js).
  - translation_profiles.py prompt wording/versions and model_config.py/provider.py
    registry shape (Sessions B/E); read their existing public functions
    (style_profile_text, render_prompt, ModelConfiguration.resolve) as fixed inputs.
  - document_draft.py's separate non-canonical demo flow (schema document-draft@1).
  - RAG, embeddings, vector search, a Story Bible, new agent orchestration.
  - Changing document_structure/segmentation schema_version or breaking any
    existing direct consumer of the current `units` shape (glossary.py,
    human_review.py, translation_memory.py, ui_decisions.py).
relevant_paths:
  - scholarly_translation/translation.py
  - scholarly_translation/document_structure.py
  - scholarly_translation/segmentation.py
  - scholarly_translation/STRUCTURE_SCHEMA.md
  - scholarly_translation/model_config.py
  - scholarly_translation/translation_profiles.py
  - scholarly_translation/source_reading.py
  - tests/test_translation.py
  - tests/test_structure_v2.py
inputs_and_fixtures:
  - Existing in-repo fixtures used by tests/test_translation.py and
    tests/test_structure_v2.py; synthetic/mock structures only, no live
    provider calls (mock adapter / provider="mock" as already used in tests).
interface_contract: >
  build_context (or its successor) must: (a) choose a translation unit
  per existing segmentation output, never re-deriving a second chapter
  model; (b) when the enclosing chapter/section node span fits within the
  model's usable_context_tokens budget (via ModelCapabilities, with
  explicit headroom reserved for instructions/glossary/local
  state/output/review metadata), pass the full chapter source text as
  context and explicitly mark the exact target span; (c) otherwise fall
  back to target unit + substantial surrounding original source (not a
  generated summary) plus relevant distant passages when needed; (d) keep
  four distinguishable layers in the rendered prompt and in the returned
  request object: TARGET SOURCE, CONTEXT SOURCE, STYLE INSTRUCTIONS,
  GLOSSARY/APPROVED DECISIONS, LOCAL STATE (five labelled sections per the
  D spec's section 5 naming); (e) keep approved_decisions/local_state/
  source_context caller-supplied fields from Session B working unchanged
  for existing callers (default None/empty), while still allowing the new
  chapter-context logic to populate source_context itself when the caller
  does not supply one; (f) extend TranslationRequest/to_metadata_dict/
  compute_cache_key with an explicit context_policy_version and enough
  recorded fields to separately answer "what exact text was translated"
  vs "what source/stored context did the model see"; (g) support an
  explicit whole-chapter-mode flag/function usable for comparison, without
  making it the default; (h) never silently invalidate a translation only
  because unrelated chapter text changed elsewhere - document and test the
  chosen invalidation rule in this file's delivery package.
acceptance_checks:
  - "python -B -m unittest discover -s tests" passes with no regression in
    the 436-test baseline (new tests add to that count).
  - A focused run of tests/test_translation.py and the new context-strategy
    tests passes in isolation.
  - A test demonstrates full-chapter-as-context behavior when the chapter
    fits the model budget, and the bounded-context fallback when it does not.
  - A test demonstrates original source preferred over any generated summary
    (no summarization code path should exist as a default).
  - A test demonstrates the three context layers (style / glossary-decisions
    / local-state) remain separable, not collapsed into one blob string.
  - A test demonstrates target-source vs context-source are independently
    recoverable from the returned request/provenance.
  - A test demonstrates model-aware budgeting using at least two different
    ModelCapabilities (small vs large usable_context_tokens) producing
    different context scope for the same structure.
  - A test demonstrates whole-chapter mode is available and distinct from
    default semantic-unit mode.
  - A test demonstrates a context selection crossing a PDF page boundary
    inside one chapter.
  - Existing cache/provenance compatibility: pre-existing cache_key callers/
    tests for Sessions B/E inputs continue to pass unchanged in meaning
    (cache_key naturally changes value once context_policy_version is added,
    but existing test expectations must be updated deliberately, not broken
    silently).
known_risks:
  - Chapter-node lookup must not assume every document has `chapter`-kind
    nodes; must degrade gracefully (fall back to bounded neighbor context)
    for flat/short documents with no chapter-level nodes.
  - Must not double-count tokens vs words; use the same conservative
    word/character counting approach already used by segmentation.py
    (STRUCTURE_SCHEMA.md) rather than inventing a second tokenizer.
source_provenance_required: true
builder_model: "Claude Sonnet 5 (sub-agent, isolated worktree)"
reason_for_model: "Scoped, well-specified implementation task within an existing contract; no demonstrated difficulty requiring Opus."
budgets:
  api_usd_hard: 0
  model_turns_hard: 0
  tool_calls_soft: 0
  wall_minutes_soft: 0
review_trigger: "Core request/cache-key schema change: conductor reviews diff before merge into main."
stop_condition: >
  Ask the conductor/user only for a genuine product/architecture choice,
  e.g. whether new chapter-context provenance should live inside the
  existing document_structure schema or as a sibling record. Routine
  implementation decisions (helper module layout, exact field names within
  this contract's interface_contract) do not require escalation.
```
