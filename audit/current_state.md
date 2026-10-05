# Current state
Updated: 2026-10-06 (Claude; untranslatable-unit fix)
UNTRANSLATABLE-UNIT FIX (user-reported stuck job, small direct fix): batch translation
validator rejected a unit containing only URLs ("target is not Hebrew"), marking the step
failed and blocking resume forever. Validator now accepts a non-Hebrew target only when
neither source nor target has a translatable word (URLs/e-mails/domains/digit tokens);
a failed step with a preserved completed response is re-validated locally on resume
(never resent); failure records now keep the specific validation reason. 803 tests OK.
No provider calls. Next exact action: user restarts UI and resumes the job.


Latest verified pre-package commit: 3c698126f24ca037f7c24a2d99e120e19ec620e2.
Fresh fetch confirmed main == origin/main before this documentation task; the prior
checkpoint's pending LIBRARY-HTML-INSTALLER push description was stale.

Current task: user requested a ready prompt package for a separate gradual-language
learning window, using copied existing Hebrew translations or uploaded Hebrew EPUB.
User explicitly permits >2 agents for this work. Contract:
audit/contracts/language_learning_prompt_package.md. Index:
LANGUAGE_LEARNING_PROMPTS_HE.md. Seven prompts under prompts/language_learning/
cover Sol, frozen handoffs, three disjoint parallel builders, sequential UI builder
and one Luna runtime generation role. No product implementation authorized by merely
creating/opening this package; no workers launched.

LEARN-PROMPTS-CHECK passed: 9 UTF-8 documents, 7 local links, example JSON parsing,
continuity/error handoffs and disjoint ownership; manual interface/dependency review.
Completion "קראתי" is the sole exactly-once global curriculum commit. Within-book
projection stays separate; the next book inherits accumulated state/effort/support.
English pilot is a visible replaceable assumption, not a chosen user language.
No linguistic critic, quizzes, paid runtime calls, or automatic mastery/level claims.
No product tests rerun for documentation-only changes. Sol internal usage unknown;
external builders/provider calls 0. No staging/commit/push for this task: unexpected
concurrent changes appeared after the initial clean check in chapter_pipeline.py,
work_journal.py, test_chapter_pipeline.py and test_pipeline_recovery_contract.py.
Those four files were not edited by this task and remain untouched. Per AGENTS.md,
Git closure stopped; documentation checks passed but the full gate is not closed.

Prior product state retained: LIBRARY-HTML-INSTALLER integrated (checkpoint reports
799 offline tests plus loopback HTML/PDF smoke; not rerun here). Actual Python install
and full library browser click-through remained unverified in that checkpoint.
LONG-DOCS/LIT-NOTEBOOK/automation accepted as scoped software; this task changed no product code.
Gate10 still blocked on representative sources/references, credentials/runtime
permission and expert quality judgment. Existing partial-export/auto-QA-after-edit/
auto-startup-dispatch gaps and uncalibrated cost/cache assumptions remain.
Existing unrelated builder worktrees and local outputs preserved.

Next exact action: deliver the saved prompt index. Git closure awaits reconciliation
of the unexpected concurrent changes by their owner; do not stage/commit them here.
Later authorized execution begins with prompts/language_learning/00_conductor.md,
frozen bootstrap before A/B/C, then sequential service/UI integration. Runtime spend
requires explicit per-book user authorization and budget; no paid pilot authorized.
