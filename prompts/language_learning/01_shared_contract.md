# LEARN shared contract — freeze before parallel work

This is the producer/consumer design to implement during LEARN-0, not an existing
API. Sol resolves it against actual repository APIs and supplies executable
learning_contracts.py plus coherent fixtures before A/B/C start. All records have
schema_version=1 and strict known-field validation. Source and prepared versions
are immutable; timestamps and generated IDs are injected at pure boundaries.
Fingerprint canonical JSON using the repository's existing safe hash conventions.

## Shared data

`LearningSource`: book_id, revision, title, source_hash, origin,
chapters[{chapter_id,title,units[{unit_id,text,kind}]}].
origin: kind="hebrew_epub"|"translation_library", original_hash,
source_job_id|null, source_revision|null. kind in each unit="heading"|"paragraph".
source_hash covers normalized ordered content AND chapter/unit identities. Source
text is Hebrew-base; embedded names/foreign quotations do not automatically fail
an otherwise Hebrew book. Empty/non-Hebrew-base/unsupported content returns a
clear unresolved result, not guessed translation. Source normalization is versioned.

`LanguageCatalog`: language, version, provenance{basis,source,license},
items[{item_id,kind,lemma,sense_he,forms,priority_tier,prerequisite_ids}],
levels[{level_id,new_items_per_chunk,max_foreign_share,max_grammar_per_chunk,
max_foreign_words_per_edit,support_mode}]. kind="word"|"phrase"|"grammar".
forms is an explicit list of allowed foreign surfaces for words/phrases; grammar
items have an explanation_he and exemplar forms in the executable frozen shape.
IDs distinguish sense and language; inflections point to one lexical item.
Catalog entries can be provisional curated-common items; basis is never a false
statistical frequency/CEFR claim. No model-written runtime catalog additions.

`LearnerState`: learner_id, language, revision, catalog_version, level_id,
support_mode, items[{item_id,introduced_count,last_completed_book_id}],
completed_books[{book_id,prepared_hash,completion_id}], active_book_id|null.
No mastery/confidence or lexical certainty inferred from reading. This is persistent
reading exposure/curriculum state. One active book per learner/language in v1.

`BookSession`: session_id, learner_id, language, book_id, source_hash,
base_learner_revision, policy_version, catalog_version, level_id, support_mode,
status="imported"|"preparing"|"ready"|"completed"|"paused"|"failed",
prepared_hash|null, chunk_ids, read_cursor|null. Current level/support are snapshotted.
Changing settings for a ready/displayed book creates a new explicit revision;
never silently rewrites it. Unprepared imported books may queue.

`ChunkPlan`: plan_id, book_id, chapter_id, chunk_id, source_hash, units,
base_learner_revision, catalog_version, policy_version, level_id, support_mode,
selected_item_ids, new_item_ids, review_item_ids, limits.
units are the exact ordered source units for this chunk, with stable unit_id.
limits copies the effective level limits. Chunking respects whole units where
possible. Deterministic planning prioritizes eligible common items/prerequisites,
then previously introduced items for recurrence; stable tie-break by item_id.
It selects candidates, not an obligation to force every candidate into the text.

`GeneratedChunk`: plan_id, response_version, provider, model, prompt_version,
input_hash, edits[{unit_id,start,end,original,replacement,item_ids,grammar_ids,
gloss_he}], warnings[{code,unit_id|null}], coverage_item_ids, content_hash.
Offsets are Python Unicode codepoint offsets into the EXACT original unit text
(not browser UTF-16 indices); end exclusive. Edits cannot overlap, cross units,
modify headings or include unplanned IDs. original must equal the exact source
slice. Apply from right to left and render untouched text verbatim with escaping.
Foreign surfaces must match selected catalog forms; use complete approved phrases
for structure. No unregistered words or inflections smuggled inside a phrase.
Longer sentence/paragraph entries become eligible only when supported by catalog
coverage at that level; unsupported higher stages stay visibly unavailable in v1.

`ChapterRecap`: chapter_id, chunk_hashes, vocabulary[{item_id,gloss_he}],
grammar[{item_id,explanation_he,examples[{chunk_id,edit_index}]}], warnings.
Coverage is computed by code from ACCEPTED edits, never the model's claim or all
selected candidates. Grammar rules link only to accepted occurrences.
No study exercise generator in v1. Recap is explanatory and unreviewed linguistically.

`CompletionReceipt`: completion_id, book_id, prepared_hash,
previous_learner_revision, next_learner_revision, completed_at.
**Explicit "קראתי" is the sole curriculum commit event.** It is legal only for
a complete ready book including every chapter's recap. Apply accepted occurrence
counts exactly once, persist level/support, mark completed and release active_book
atomically. Preserve previously introduced items; never replace accumulated state
with only the last book. Increment learner revision once. Duplicate completion of
the same prepared version returns its stored receipt with no additional writes.
Conflicting base revision/prepared_hash returns state_conflict. Partial preparation,
viewing, downloads, cursor updates and model output never commit curriculum.

No automatic upward level transition: completion continues the selected level;
reader explicitly chooses another level for the next book. Newly eligible items
are still selected incrementally within limits. The next plan uses the full committed
LearnerState, not a freshly initialized list. Closing a ready book does not reset it.

## Public Python handoffs (frozen in LEARN-0)

Shared validation constructors/helpers live in learning_contracts.py (Sol owns).
Functions below return validated plain data or a typed/code-bearing LearningError.
Modules stay small; no unused interface registry or scaffolding.

A:
- learning_catalog.load_catalog(language) -> LanguageCatalog; unsupported_language explicit.
- learning_planner.plan_book(source, learner, catalog, *, policy_version) -> list[ChunkPlan].
- learning_planner.replan_chunk(provisional_plan, projected_learner, catalog)
  -> final ChunkPlan. plan_book freezes chunk boundaries and provisional candidates;
  call replan_chunk sequentially before each generation using accepted earlier
  chunk occurrences. Keep base_learner_revision tied to the committed start state;
  final plan_id/hash include the effective projection. Do not pre-generate all chunks
  against one unchanged new-item list. Skipped candidates never become introduced.
- learning_state.apply_completion(learner, session, generated_chunks, recaps,
  *, completion_id, completed_at) -> (LearnerState, CompletionReceipt), pure.
- learning_store.LearningStore(root): save_source/get_source,
  create_session/get_session/list_sessions, get_learner/save_prepared,
  complete_book(session_id, expected_prepared_hash, completion_id), save_cursor.
  Sol fixes exact arguments in the executable bootstrap for B/C consumers.
  Store serializes mutations per learner/language and persists learner + session +
  receipt as one recoverable transaction. Atomicity must include crash consistency,
  not just one in-memory lock and independent file replacements. Single-state
  aggregate or existing transaction primitive is sufficient; no database framework.

B:
- learning_import.import_hebrew_epub(path_or_bytes, *, book_id, title=None) -> LearningSource.
- learning_import.import_translation_job(job_snapshot, *, book_id) -> LearningSource.
  Input is a server-resolved complete immutable snapshot of current Hebrew targets,
  including saved edits and canonical order. Browser sends job_id only. Sol inspects
  actual job shapes and supplies the snapshot resolver; B does not modify web_ui.py.
  Missing target text fails explicitly; no original-language fallback.

C:
- learning_generation.build_request(plan, catalog, context) -> resolved request + fingerprint.
- learning_generation.generate_chunk(plan, catalog, context, *, controlled_generate)
  -> GeneratedChunk plus proposed recap entries. Callable owns actual paid dispatch,
  reservation and journal outside this function; no direct/uncontrolled provider call.
- learning_generation.build_chapter_recap(chapter_id, accepted_chunks,
  proposed_entries) -> ChapterRecap, deterministic filter/merge, no extra model call.
- learning_render.render_chunk(source_units, generated_chunk, support_mode)
  -> escaped HTML fragment with stable occurrence IDs and <bdi lang=...>.
  No executable markup from source/model. Python handles edit offsets.

Generate each chunk with the same Luna role and one structured response containing
edits + recap proposals; chapter recap merges these locally. No lexical-selection
model, keeper, reviewer or second generation for recap. Explicitly rejected model
output pauses/fails the chunk; no silent success or automatic repair loop.

## Learning window HTTP action contract (Sol implementation, D consumer)

All JSON responses: `{ok:true,data:...}` or `{ok:false,error:{code,message_he}}`.
Use existing session token + same-origin safeguards. Mutations use POST. IDs are
validated server-side; never accept filesystem paths/credentials in stored objects.
Routes below are proposals until Sol freezes them with actual upload/token behavior.

- GET /learning: separate learning page, its own script/CSS and session bootstrap.
- POST /learning/library: `{}` -> learner summary + queued/active/completed books.
- POST /learning/import-translation: `{job_id}` -> copied source/book identity.
- POST /learning/upload-epub: protected upload using existing transfer conventions
  -> copied source/book identity, with errors for invalid/empty/unsupported EPUB.
- POST /learning/settings: `{language,level_id,support_mode}` -> settings for NEXT
  preparation; reject conflict with an active preparing book. Never rewrite ready text.
- POST /learning/prepare: `{book_id,budget_usd,authorization_id}` -> session/job id;
  server resolves chosen model and current in-memory credentials. Require finite
  positive user budget and existing authorization; no model call on import/open.
- POST /learning/status: `{session_id}` -> stage/status and safe cost summary.
- POST /learning/chapter: `{session_id,chapter_id}` -> escaped reading HTML + recap.
- POST /learning/cursor: `{session_id,chapter_id,unit_id}` -> cursor only.
- POST /learning/complete: `{session_id,expected_prepared_hash,completion_id}`
  -> CompletionReceipt + new safe learner summary; ready only, idempotent.

No live-generation API keys in query strings/localStorage/persistent settings.
Existing credential setup may be reused with a simple link/control in the learning
window; avoid requiring a translation job to authorize a learning run.

## Errors, dependencies and acceptance

Error codes include unsupported_language, invalid_epub, no_hebrew_text,
incomplete_translation, invalid_plan, invalid_generation, missing_recap,
active_book_conflict, state_conflict, budget_exhausted, credentials_required,
unknown_dispatch and corrupt_store. Failures never advance LearnerState.
Missing suitable slots is honest coverage-shortfall data, not a reason to invent text.

Cache identity includes source hash, ordered chunk input, learner snapshot/effective
plan hash, catalog/policy/prompt versions, context hash, provider/model/settings.
Received responses persist under the existing journal before parse/accounting.
Replay of a valid saved response makes zero model calls and changes no learner state.
Book preparation uses a local projected state for within-book recurrence only;
later chunks may reuse items accepted earlier in that book. Projection does not
persist as global learning until completion; use accepted edits, not planned guesses.
Generation is therefore sequential within a book even if preparation plan is precomputed.
Freeze numeric level limits and the effective counting convention in LEARN-0 before
parallel dispatch. Advanced levels can remain unavailable until enough catalog
forms exist; do not expand into a target-language grammar engine to enable them.

Acceptance includes: two books with continuity, repeat completion, concurrent
completion, crash/restart, stale versions, no duplicate provider replay, source
immutability, Hebrew EPUB/library equivalence, rank/dependency choices, bad spans,
unknown IDs, load beyond quotas, invalid recaps, escaped RTL rendering and legacy UI.
