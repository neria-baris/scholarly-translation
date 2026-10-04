# User addendum, 2026-10-05: Cross-Chapter Persistent Translation State Integration

Verbatim user instruction received mid-session (preserved for provenance;
referenced by audit/contracts/session_d2_persistent_document_state.md).

---

## ADDENDUM — Cross-Chapter Persistent Translation State Integration

The overall implementation must support translation of multi-chapter books and long documents while preserving translation decisions, terminology, voice/register, definitions, character information, and unresolved ambiguities across chapters.

Session D has already been instructed to implement the persistent cross-chapter context/state mechanism.

Session C may already have completed its chapter-level QA implementation. DO NOT rerun or restart Session C solely for this feature.

Instead, the final integration agent (Session G) owns the integration between Session C's existing chapter-level QA and Session D's new persistent document state.

### Required final behavior

The integrated pipeline should operate conceptually as:

Document structure
    ↓
Translation of semantic units using:
    - profile/style instructions
    - persistent document state
    - current chapter context
    - local translation state
    ↓
Assemble complete translated chapter
    ↓
Chapter-level QA
    ↓
Proposed persistent-state updates
    ↓
Validate / merge state updates
    ↓
Persist new versioned document state
    ↓
Translate next chapter using the updated state

The system must NOT repeatedly send all previous chapters as context.

---

## Responsibility of Session G

During final integration, inspect the implementations produced by Sessions C and D and connect them with the smallest clean interface necessary.

Session G must ensure that chapter-level QA can produce or trigger proposed updates to persistent document state.

Do not redesign Session C from scratch.

Adapt its existing chapter-QA output or add a small integration layer.

### Chapter QA → persistent-state update categories

For scholarly documents, chapter-level QA should be able to propose:

- new or changed terminology decisions;
- definitions that should persist;
- technical notation and symbols;
- author-specific terminology usage;
- important conceptual distinctions;
- recurring names/titles;
- unresolved interpretive ambiguities;
- contradictions with previously stored state.

For literary documents, chapter-level QA should be able to propose:

- character names and established Hebrew spellings;
- forms of address;
- stable character voice/register information;
- narrator style/register;
- recurring expressions;
- invented terminology;
- place names;
- translation-relevant relationships;
- recurring motifs when they materially affect translation;
- unresolved ambiguities;
- contradictions with existing state.

Do not store arbitrary plot summaries or chapter summaries.

Only information likely to affect future translation should become persistent state.

---

## Source-backed state

Session G must verify that persistent state remains source-backed.

Where practical, every substantive persistent item should reference:

- source chapter;
- source block/unit;
- source span or equivalent provenance.

Do not allow an unsupported model inference to silently become an established fact.

Support explicit certainty/status such as:

- established
- likely
- unresolved

When a later translation materially depends on an earlier state item, the system should be able to provide the relevant original source span alongside the summarized state.

---

## State updates

The chapter-level QA stage should produce candidate updates rather than mutating persistent state invisibly.

A minimal conceptual flow is:

existing_document_state
+
chapter_translation
+
chapter_source
+
chapter_QA
→
proposed_state_updates

Then:

validate / reconcile proposed updates
→
new versioned document_state

The implementation does not need a complex approval workflow.

Use the simplest mechanism compatible with the project's existing provenance/versioning design.

---

## Versioning and reproducibility

Session G must verify:

- persistent document state is versioned;
- each translation unit records which document-state version it received;
- historical translations remain reproducible;
- updating state for Chapter N+1 does not rewrite the context record of Chapter N;
- state provenance remains separate from raw source provenance.

---

## Context hierarchy

The final integrated system should preserve four distinct layers:

1. PROFILE / STYLE INSTRUCTIONS
2. PERSISTENT DOCUMENT STATE
3. CURRENT CHAPTER SOURCE CONTEXT
4. LOCAL TRANSLATION STATE

Do not collapse these into one generated summary.

The original source remains authoritative.

---

## Interaction with translation profiles

For scholarly translation:
persistent state primarily preserves terminology, definitions, notation, conceptual distinctions, and prior translation decisions.

For literary translation:
persistent state primarily preserves voice/register, names, forms of address, recurring expressions, relevant character continuity, and translation decisions.

Do not duplicate translation-profile prompt logic inside the persistent-state implementation.

---

## Final integration tests

Session G must add or update tests demonstrating at least:

1. A multi-chapter document carries an approved terminology choice from one chapter into the next.
2. A literary character's established name/form of address/register can persist across chapters.
3. Chapter QA can propose a persistent-state update.
4. A persistent-state item retains source provenance.
5. An unresolved ambiguity remains unresolved rather than becoming an established fact.
6. A contradiction between new chapter information and existing state is surfaced rather than silently overwritten.
7. Each translation records the persistent-state version it used.
8. Updating document state does not invalidate historical reproducibility.
9. The next chapter receives the updated state.
10. Arbitrary chapter summaries are not accumulated as persistent memory.

---

## Session G scope

Session G is still a FINAL INTEGRATION AND REPAIR agent.

It should:

- inspect outputs from A–F;
- connect compatible components;
- fix concrete integration defects;
- add missing adapters/interfaces;
- update tests;
- run the full relevant test suite.

It should NOT:

- redesign the whole architecture;
- rebuild Session C from scratch;
- add a large Story Bible;
- add vector search or RAG;
- create a second memory framework;
- introduce unrelated features.

If Session C's existing chapter QA cannot directly emit state updates, add the smallest adapter or structured output extension required.

At completion, Session G must explicitly report:

1. how chapter QA feeds persistent document state;
2. what information persists across chapters;
3. how source provenance is retained;
4. how uncertainty is represented;
5. how state versions affect translation provenance;
6. any remaining limitations for very long books/documents.

Do not rerun Session C for cross-chapter memory work. Session D implements the persistent-state mechanism; Session G integrates the already-completed chapter-QA work from C with D's persistent state.
