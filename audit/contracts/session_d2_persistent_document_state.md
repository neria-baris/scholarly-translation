# Session D2 — Persistent Cross-Chapter Document State

> Status: fulfilled. Before this contract was handed to a separate sub-agent,
> the already-running Session D builder (worktree-agent-ac188145aaddcd523)
> was itself resumed with the user's 2026-10-05 addendum and implemented this
> scope directly, stacked on its own earlier commit (`c881e9c` ->
> `e6843c2`): new `scholarly_translation/document_state.py` plus `translation.py`
> wiring, `tests/test_document_state.py` (19 tests). Conductor independently
> reviewed the diff and reran the full suite in that worktree (475 tests,
> 1 skip) before merging as part of the same Session D integration. No
> separate D2 sub-agent was launched; this file is kept as the scoping
> record this work is judged against, not as a still-open task.

```yaml
task_id: session_d2_persistent_document_state
milestone: "D2 — Persistent cross-chapter document state (addendum, 2026-10-05)"
objective: >
  Build a versioned, source-backed, persistent document-state mechanism so a
  multi-chapter translation can carry terminology/definition/notation
  decisions (scholarly) or character name/register/recurring-expression
  decisions (literary) and unresolved ambiguities forward from chapter to
  chapter, WITHOUT resending all previous chapters as context. This is new
  work: the already-merged Session D (commit 89adbd76, context_strategy.py)
  implemented only chapter-aware context sizing (whole-chapter-if-it-fits vs
  bounded fallback within one chapter); it does not persist anything across
  chapters. This contract is scoped exactly to the addendum the user supplied
  on 2026-10-05, titled "Cross-Chapter Persistent Translation State
  Integration". Read that addendum in full (reproduced in
  audit/raw/addendum_2026-10-05_persistent_state.md) before starting.
in_scope:
  - A new module scholarly_translation/document_state.py owning: a typed,
    versioned state-item record; a pure propose/validate/merge function
    turning (existing_state_snapshot, proposed_updates) into a new
    immutable state_version snapshot; contradiction surfacing (a new
    proposed item conflicting with an existing `established` item is
    flagged, never silently overwritten); explicit certainty levels
    (`established`/`likely`/`unresolved`); and per-item source provenance
    (document/chapter/unit/node reference, never a bare guess).
  - Extending scholarly_translation/translation.py /
    scholarly_translation/context_strategy.py to accept an optional
    resolved document-state snapshot as a fourth, separately labelled
    prompt layer (PERSISTENT DOCUMENT STATE), distinct from STYLE
    instructions, CURRENT CHAPTER SOURCE CONTEXT (Session D's existing
    context_segments), and LOCAL TRANSLATION STATE (existing `local_state`
    field from Session B/Gate 12). Do not collapse these into one blob.
    Keep the existing `approved_decisions`/`local_state`/`source_context`
    fields and their current callers working unchanged when the new
    parameter is omitted (default None/no-op, matching every prior
    session's backward-compatibility convention in this file).
  - Recording which document-state version a translation request/result
    used (`to_metadata_dict`, `compute_cache_key`), so historical
    translations stay reproducible: updating state for chapter N+1 must
    never rewrite or invalidate chapter N's recorded state version or
    provenance. State provenance is a field separate from raw source
    provenance (document/page/unit/node ids), never merged into it.
  - tests/test_document_state.py and targeted additions to
    tests/test_translation.py / tests/test_context_strategy.py for the new
    prompt layer and cache/provenance fields.
out_of_scope (explicitly deferred to Session G, per the addendum):
  - Any change to scholarly_translation/review_qa.py or
    scholarly_translation/semantic_review.py (Session C's chapter QA). Do
    not rerun or redesign Session C. This session must NOT wire chapter-QA
    output into the propose/merge function itself - only Session G does
    that integration, using the smallest adapter necessary. This session's
    own tests exercise propose/validate/merge with direct, synthetic
    proposed-update objects, not through review_qa.py.
  - UI (Session F), PDF/EPUB export (Session X - disjoint files, runs in
    parallel with this session).
  - Reimplementing or duplicating scholarly_translation/glossary.py's
    existing approved/proposed terminology-rule mechanism (Gate 5). The new
    store is for the broader addendum categories (definitions, notation,
    conceptual distinctions, character voice/register, forms of address,
    recurring expressions, unresolved ambiguities, contradictions) and must
    not replace or re-approve glossary rules; reuse glossary.py read-only
    if a cross-reference is genuinely useful, otherwise keep the two
    systems separate.
  - Duplicating translation_profiles.py prompt wording/logic inside the
    state implementation (addendum's explicit "do not duplicate" rule):
    the state store holds categorized items, it does not itself decide
    scholarly-vs-literary phrasing.
  - A large Story Bible, vector search/embeddings/RAG, a second independent
    memory/orchestration framework, or any approval-workflow UI. Use the
    simplest mechanism compatible with this project's existing
    provenance/versioning design (see e.g. how `unit_policy` and
    `glossary` rule versions are persisted today).
relevant_paths:
  - scholarly_translation/translation.py
  - scholarly_translation/context_strategy.py
  - scholarly_translation/document_structure.py (read-only: node/chapter ids)
  - scholarly_translation/glossary.py (read-only reference only)
  - scholarly_translation/translation_profiles.py (read-only reference only)
  - scholarly_translation/review_qa.py (read-only reference only - inspect
    its ChapterQARequest/run_chapter_qa output shape at
    scholarly_translation/review_qa.py:593-761 so the new state-item schema
    is realistically shaped to later accept Session G's adapted output, but
    do not modify this file)
  - tests/test_translation.py
  - tests/test_context_strategy.py
inputs_and_fixtures:
  - Synthetic structures/units already used by tests/test_translation.py
    and tests/test_context_strategy.py; synthetic proposed-update objects
    you define yourself for this session's own tests. No live provider
    calls.
interface_contract: >
  A `DocumentState` snapshot is immutable and carries an explicit
  `state_version` (monotonically increasing per document) and an ordered
  collection of state items, each with: `item_id`, `category` (free-text or
  small allowlist covering the addendum's scholarly/literary categories),
  `content`, `certainty` (`established`/`likely`/`unresolved`),
  `source_chapter_id`/`source_unit_id`/`source_span_or_node_ids`, and
  `introduced_in_version`/`superseded_in_version` (nullable) so old
  snapshots remain fully reconstructable. `propose_state_update(existing,
  proposed_items)` returns `(new_state_or_None, outcomes)` where each
  outcome says accepted/superseded/contradiction_flagged/rejected with a
  reason; a contradiction against an `established` item is surfaced in
  `outcomes`, never auto-resolved, and does not silently mutate the
  existing item. `render_state_for_prompt(snapshot, chapter_id)` returns a
  bounded textual rendering of only the items relevant/applicable so far
  (never the full chapter history, never a generated summary of chapters -
  items are themselves the compact carried-forward facts). Translation
  request builders accept an optional `document_state` snapshot (and
  resolve its version into cache key + metadata) without requiring every
  caller to pass one.
acceptance_checks:
  - "python -B -m unittest discover -s tests" passes with no regression
    against this session's starting baseline (no new failures; record the
    exact before/after counts in your delivery report).
  - A test demonstrates an approved terminology/definition decision
    introduced in one synthetic "chapter" state update is visible/rendered
    when building a request for a later chapter, without resending the
    earlier chapter's full source text as context.
  - A test demonstrates a literary character's established name/register
    decision persists the same way.
  - A test demonstrates a proposed update with `unresolved` certainty
    remains `unresolved` in the resulting snapshot (never silently promoted
    to `established`).
  - A test demonstrates a contradiction (new item vs. an existing
    `established` item in the same category/key) is surfaced in the
    propose/merge outcome rather than silently overwriting the prior item.
  - A test demonstrates every state item carries source provenance
    (chapter/unit/span or node ids), and that an item without any
    provenance is rejected rather than accepted as a bare model guess.
  - A test demonstrates a translation request/result records the exact
    document-state version it used, and that creating state_version N+1
    does not alter the recorded version/content of a request that used
    state_version N (historical reproducibility).
  - A test demonstrates the four layers (profile/style, persistent document
    state, current chapter source context, local translation state) remain
    separately labelled/recoverable in the rendered prompt and in the
    request's provenance, not collapsed into one blob.
  - A test demonstrates that building a request for chapter K+1 does not
    require re-passing chapters 1..K-1's source text - only the current
    state snapshot (which is bounded, not O(chapters)).
known_risks:
  - Keep the state-item schema simple and additive now; the richer
    "chapter QA emits structured proposals" wiring is Session G's explicit
    responsibility per the addendum - do not pre-build that adapter here,
    but do keep this session's public functions easy for G to call with
    whatever shape G extracts from review_qa.py's `issues`/
    `chapter_level_notes`.
  - Must not make `document_state` mandatory for existing callers of
    `build_translation_request`/`build_context` - every existing test and
    caller must keep passing unchanged when it is omitted.
source_provenance_required: true
builder_model: "Claude Sonnet 5 (sub-agent, isolated worktree)"
reason_for_model: "Scoped, well-specified implementation task within an existing contract; no demonstrated difficulty requiring Opus."
budgets:
  api_usd_hard: 0
  model_turns_hard: 0
  tool_calls_soft: 0
  wall_minutes_soft: 0
review_trigger: "New persisted schema and core request/cache-key change: conductor reviews diff before merge into main."
stop_condition: >
  Ask the conductor/user only for a genuine product/architecture choice not
  already settled by the addendum or this contract. Routine implementation
  decisions (exact field names/module layout within this contract's
  interface_contract) do not require escalation.
```
