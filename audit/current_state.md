# Current state — ROMAN-PAGES fix on main (not pushed); LEARN-PARALLEL uncommitted in the working tree
Updated: 2026-10-11. Claude Code primary agent (conductor), user request: chapter-translate failed "translation response target is not Hebrew".

Cause: EPUB page-number markers are separate units; Roman numerals (ii, iii, iv, viii, ix) counted as translatable words, so the model's correct passthrough answer was rejected. Not caused by REVIEW-SUGGESTIONS.
Fix: formal_checks.has_translatable_words treats a single-case Roman numeral as a number ("mix" stays a word); test in tests/test_scholarly_math.py. The preserved response of job 4c96b48b3c9c15e369152c2855a0d40d (288 items) passes the new validator offline, so Resume re-validates it without a new provider call.

Verification: scholarly_math, target_languages, chapter_pipeline, formal, draft and structure suites OK. Full suite 1487: 2 failures in learning tests, which belong to Codex's uncommitted LEARN-PARALLEL work (test_learning_store passes on HEAD). Runtime provider calls 0.

Concurrent work: Codex LEARN-PARALLEL (learning_*, web_ui.py, learning tests, audit logs, new contracts/files) is uncommitted in this same working tree and was not staged. Its own checkpoint is in the working copy of this file.

Active delegated work: none.

Next action: user restarts the web UI and clicks Resume on the failed book; Codex (or the conductor) reviews and commits LEARN-PARALLEL on top of this commit; push main when the user approves.

---
Previous checkpoint:
# Current state — REVIEW-SUGGESTIONS on main (not pushed)
Updated: 2026-10-10. Claude Code primary agent (conductor), user request: apply review suggestions automatically (also in finished books) and avoid over-literal translation.

Main: REVIEW-SUGGESTIONS commit on 6055666 COMIC. Not pushed (origin/main = 7a06f80; COMIC, SINGLE-INSTANCE and this commit are local). Contract audit/contracts/review_suggestions.md.

Done: every unit-review suggestion and chapter-QA Hebrew-quality finding is corrected automatically (consistency/continuity only when MAJOR/CRITICAL); each issue sent once; human edits never overwritten. Finished books show "הצעות התיקון של הבדיקה" on the result page: the button reopens chapters (no call), Resume runs the corrections + rechecks (paid, ~$0.01-0.30 per local book at list price). Translator profiles (scholarly v2@6, literary v2@5) and the Hebrew pack now require idiomatic structure; reviewer/QA flag calques.

Verification: full offline suite 1486 OK. Runtime provider calls 0.

Open:
- The running web_ui server must be restarted to load the new code (single-instance lock: stop the old server, start one).
- Finished books were reviewed with the old reviewer prompt; calque detection applies to new reviews only (re-review of finished books is out of scope unless the user asks).
- Real-comic quality BLOCKED (user pages + paid-run approval). Builder worktrees from COMIC remain (.claude/worktrees/agent-*), safe to remove after user confirmation.

Active delegated work: none.

Next action: restart the web UI; the user opens each finished book and clicks the suggestions button, then Resume; push main when the user approves.
