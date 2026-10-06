# LEARN-6 — same-call vocabulary growth and five-language learning

User explicitly authorizes implementing LEARN-5 expansion direction. Isolated
feature only; no active main checkout/server/data/credentials access, merge or deploy.
Single Luna generation role remains; no critic or dictionary model or paid pilot.

Inputs: existing schema1 source, learner/session/plan/catalog. New policy3 uses
prompt learning-generation@3/new runtime asset10; policy1/2 assets and stage/hash
behavior remain readable/replayable. Existing French catalogs unchanged. Other
languages de/es/yi/it use version <language>-seed@1 with empty teaching items,
DEFAULT_LEVELS and frequency_seed from pinned european_500.json. Catalog validator
allows empty items and optional frequency_seed (list of {rank,word}); no placeholder
Hebrew translations. French can expose frequency_seed too, but legacy requests
must keep prior instruction/data/hash identity. At most100 frequency hints per
new-policy request; prioritize frequent everyday items and common grammar by
model judgment, context and level.500 is a milestone, no dictionary ceiling.

Output: response_version1 unchanged; policy3 optionally accepts introduced_items
(array, max new_items_per_chunk). Each proposal has exactly item_id(local ref),
kind(word/phrase/grammar),lemma,sense_he,forms,explanation_he. Nonempty Hebrew sense;
grammar explanation required. All proposals must be used by accepted edits. Map
local refs to application-assigned stable IDs <lang>-learn-<24hex> derived from
normalized kind/lemma/sense/forms/explanation and language, not model-chosen ID.
Application sets priority_tier from matching seed form else501, min_level current
level, prerequisite_ids[]. Existing IDs/definitions cannot be overwritten;
duplicate aliases/definitions, unknown refs, oversized items, wrong-script foreign
forms, invalid/overlapping spans and quota overflow refused. Only word/phrase IDs
in item_ids, grammar IDs in grammar_ids; existing form/grounding checks retained.
Combined new known-catalog and proposal objectives count against new quota and
new-density/grammar/edit limits; recurring known items still outside new quotas.
Grammar proposals must match actual allowed foreign forms in accepted edits;
no unsupported grammar recap. Recap refs remapped, merged locally; if needed,
fallback to accepted item metadata only, no extra model call.

Persistence: GeneratedChunk optional introduced_items contains admitted catalog
items (ordinary nine-field catalog shape), with provider/model/prompt/input_hash
already on the chunk; definitions included in content_hash. Learner and Session
optional vocabulary list contains {item:<nine-field item>,origin:{provider,model,
prompt_version,input_hash}}. Missing vocabulary means[], legacy JSON unchanged.
New session snapshots learner vocabulary. New accepted definitions project into
job.projected vocabulary for later chunks, stored with normal service checkpoint.
Prepared data contains definitions for restart/reader/recap. Completion promotes
only accepted definitions into learner vocabulary atomically with existing history,
once; abandonment never promotes. Existing definition and first origin retained.
No source/old prepared mutation; detect conflicting ID/definition, wrong language.
effective_catalog(base, vocabulary, chunks=()) merges without redefining IDs;
used by start/replan/reader/progress and inactive catalog compatibility check.

Language selection: service.json additive selected_language, default fr. All five
available. select_language(code) refuses while ANY non-abandoned imported/preparing/
paused/failed/ready session owns an active slot. Per-language learner history and
effort isolated. summary learner/progress/levels for selected language, sessions
and jobs filtered to selected language, books shared imports; expose
selected_language. HTTP POST /learning/language accepts language; defaults of old
methods preserved. set_effort/start use selected language; resume/reader pinned
session language. Existing readers work after switching. Unknown code explicit.
UI selector near effort, disabled during active book, honest model-derived labels,
no curator quality claim. Reader/recap/vocab/click gloss language/direction from
selected or session language (yi RTL and combining marks). Preserve all source,
budget/key, polling, click option, progress/search and completion flows.

Ownership/common base: one scoped Claude Sonnet builder G owns
learning_contracts/catalog/planner/generation/state/store.py, new
learning_vocabulary.py, runtime_prompts/10_learning_open_vocabulary.md and
tests/test_learning_open_vocabulary.py only. Sol owns learning_service.py,
web_ui.py, learning.html/js/css, other integration/UI/HTTP tests, README and audit.
Sequential integration; separate worktree common committed contract; no recursive
delegation. G bounded one invocation max2 USD list enforced CLI cap, no Bash/network/
Git/tests/audit edits. Sol tests, reviews diffs and commits. No Astra/Opus planned.

Acceptance: all learning tests plus affected HTTP/library handoff tests and JS
syntax, no blanket full-suite rerun unless evidence shows shared regression.
Fake adapter one call per chunk: proposal/reuse/complete/reopen/next-book continuity
and >500 growth; invalid proposals/ref/unused/quotas/script/spans; legacy1/2;
language switching/history isolation and active guard; five languages including
yi direction; cached replay/pause/restart no duplicate calls; browser selector,
new word/list/click and explicit completion on synthetic data. Software acceptance
only, actual language/pedagogical quality unverified; no paid runtime pilot.
Errors: invalid_generation/invalid_record/catalog_changed/unsupported_language/
active_book_conflict. Side effects: isolated local history and current controlled
generation/cache/budget; no automatic preparation on import/selection.
Local clean reviewed feature commit/receipt, push not attempted, main unchanged.
