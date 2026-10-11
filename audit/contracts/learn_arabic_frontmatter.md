# LEARN-ARABIC-FRONTMATTER

Authorized 2026-10-11; direct conductor implementation, no provider calls.
Owns learning catalog/script/rendering and session-specific initial-chapter exclusion.
Input/output: schema-1 records gain optional immutable skip_initial_chapters
(integer, default 0) and plan learning_excluded (boolean). Existing records retain
their original behavior. Arabic uses Modern Standard Arabic, native script, RTL,
and a locally authored starter list (not a corpus frequency claim).
Excluded prefix remains original Hebrew in reader/exports, with deterministic
local empty chunks to preserve source/unit coverage; no calls, lessons, exposure,
dictionary entries or learning word allowance. Setting is chosen before preparation,
pinned across recovery/resume, and must leave at least one learning chapter.
Errors: invalid count/type, changed setting, forged exclusion/edits fail explicitly.
Side effects: local code/tests/audit and existing session persistence only.
Acceptance: Arabic lifecycle/script/RTL export, prefix call exclusion, budget word
denominator, intact exports, restart, negative validation, legacy regression.
Out of scope: automatic semantic frontmatter classification, paid quality review,
changing imported segmentation, deleting frontmatter. Git closure remains blocked
by previously observed unrelated math changes; no staging/commit/push until resolved.

2026-10-11 follow-up: live old process served updated static UI with old five-
language/chapter-less state, producing an empty native selector. Add compatibility
notice and disable preparation until languages/chapter choices are available;
verify in the user's live browser without provider dispatch. ROMAN-PAGES ownership
was reconciled and committed by the other conductor as e035107, resolving Git blocker.
