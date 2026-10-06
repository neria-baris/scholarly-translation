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

## 2026-10-06 — user-directed preparation controls, help and archive extension

User extends this gate: expose adjustable budget/context/output, preserve long
and partial data with visible warnings, dedicated help, and all received grammar
alongside personal vocabulary. The user's explicit removal of the two-subagent
limit supersedes that development guideline for this task. Disjoint ownership,
shared contracts and sequential integration still apply; no extra agent is
required solely to use concurrency.

Ownership amendment: external G failed ConnectionRefused (zero observed tokens/
list cost); escalation retry was rejected by automatic approval review because
it could export repository implementation context to external Claude. No external
retry/workaround. Sol implements G scope locally. Local help_archive agent owns
only learning_archive.py, learning_help.html and test_learning_archive.py in the
separate learning-g checkout; Sol copies/reviews/integrates them sequentially.
No third-party review, runtime calls or active main access.

Controls: start/resume additive context_chars/output_tokens/retry; default4000/
6000/false, old job defaults0/6000. Positive finite user budget removes former100
USD limit. Context0..2,000,000 chars is explicit; source chunks are complete.
Return requested/provided/available context accounting. Physical model window/
output ceilings remain explicit errors, never silent trimming. Resume changes
only pending input; accepted chunks immutable. Explicit retry changes call
dependency identity, preserves journal/raw results, creates separate control
ledger epoch. Sum prior spent plus uncertain held across all epochs before new
allowance. Never ignore corrupt accounting; report accounting_unavailable and
refuse fresh generation. Truncated/failed raw responses remain journaled; no
automatic resend, false completed chunk or clearing prior costs.

Archive: save_personal_archive(root, language, progress, chapter=None), schema1
dictionary completed/current rows and immutable chapter recap including actual
received explanations/examples, IDs and safe item labels. JSON and Markdown,
fsync/atomic replacement per file, local serialization, no text truncation.
Dedicated root/personal/<language>/grammar next to dictionary files. Reader
archives before returning; cursor/completion update dictionary. Identical chapter
reuse repairs missing companion; differing same-identity recap never overwrites.
Archive error visible and retryable while reading/atomic completion remain usable.
One process per learning root; no claim of cross-file transaction/cross-process
support. HTTP GET /learning/help with RTL static help; progress shows archive path
and warnings. Help includes languages, effort/continuity, context/click, progress,
budgets/output/retries, storage/quality/privacy and source handoff.

Acceptance additions: five-language >500 lifecycle, actual grammar reader/archive
integration, 180k+ long grammar preservation, archive write failure/retry/identity,
budget1000 resume, context50000, truncated raw retention/explicit retry/held costs,
physical output rejection/corrupt ledger visibility; help and resume HTTP/token
boundary, synthetic browser selector/options/help/grammar/progress/click. Scoped
learning and affected library tests only; no blanket translation suite rerun.

Final unknown-outcome refinement: a retry checkbox authorizes retiring only the
currently unknown/dispatched journal steps into failed with an explicit reason.
Keep identities/events/held costs, distinct new retry identity, and checkpoint
consumption of this one-use authorization before another call. A subsequent lost
call requires a new user choice; persisted retry revision alone grants nothing.
Acceptance: simulated transport loss, default resume no call, explicit retry
continues with prior hold and old failed evidence, second loss again refuses
automatic resend. No changes to shared WorkJournal/control/pipeline modules.
