# Builder A — deterministic curriculum, learner state and storage

Read LANGUAGE_LEARNING_PROMPTS_HE.md, 01_shared_contract.md, AGENTS.md and your
scoped audit/contracts/learn_1.md. Use the conductor-provided frozen bootstrap
commit and learning_contracts.py fixtures. Other workers B/C are writing isolated
paths concurrently; do not edit their paths or shared contracts.

## Owns

New scholarly_translation/learning_catalog.py, learning_planner.py,
learning_state.py, learning_store.py, learning_data/fr_common_v1.json;
tests/test_learning_state.py, test_learning_planner.py, test_learning_store.py.
No web/UI/provider/EPUB/schema/audit/policy/dependency changes. No paid calls,
recursive delegation, Git operations, generated private fixtures or broad refactor.

## Implement

1. Small explicit French first-slice catalog with words/phrases and grammar items,
   priority tiers, prerequisite IDs, approved surfaces and provenance/license.
   Use the attached wordlists/README_HE.md and european_500.json as the frequency
   candidate source. User selected fr/de/es/yi/it lists; French is the proposed
   first implementation slice, not authorization to fake support for the other four.
   Preserve actual source rank/license, distinguish surface forms from lemma/sense,
   and add Hebrew glosses/allowed forms for the working starter subset. Hand-authored
   grammar/semantic additions need separate curated_common provenance. No crawler,
   runtime list download or blind translation of function words. Do not copy
   proprietary lists. Reject unsupported language catalogs explicitly.
2. Pure planner: stable common-first/prerequisite selection and new/review quotas;
   whole-unit chunks bounded independently of chapter length. Select eligible
   candidates; don't force replacements into unsuitable contexts. No LLM selection.
   Same input gives identical plan, hashes and ordering. Select only levels the
   seed actually supports; no deceptive fully supported advanced levels.
3. Immutable, versioned learner/session updates and deterministic within-book
   projected exposure. Catalog/policy/settings and source dependencies explicit.
   Imported books queue; one active preparation/ready book per language.
4. "קראתי" exactly-once aggregate transaction: ready book plus all accepted chunks
   and recaps, matching expected prepared hash/base revision, union prior items
   with accepted occurrences, preserve selected effort/support and completion history.
   Never infer mastery, never auto-increase effort and never erase older items.
   Repeated clicks return the original receipt. Stale/conflicting completion fails.
5. Small local store under caller-supplied ignored outputs/learning. Validate IDs
   and containment; serialize mutations and use recoverable atomic persisted state.
   Persist source/generated records separately as immutable blobs referenced by
   hash, with one aggregate commit for learner/session/receipt when completing.
   Cursor is separate progress and cannot mark complete. Restart reconstructs
   the exact reading/version and continuity without generation.

## Acceptance

Meaningful offline tests for: common-first selection and grammar prerequisites;
new/review limits on short and long chapters; snapshot/level consistency;
completion → next book carrying all previously introduced words/grammar;
duplicate and concurrent completion; simulated interruption at persistence boundary;
stale prepared hash/base state; corrupt store/path containment; cursor/open/import
does not advance curriculum; no claims of mastery or automatic level promotion.

Report changed_files, implemented handoffs, actual commands/results or not_run,
deviations, open_risks and observable model usage. Stop at your scoped implementation.
If a schema mismatch prevents correct work, report it to Sol with one minimal
proposal; do not silently invent fields or modify another worker's files.
