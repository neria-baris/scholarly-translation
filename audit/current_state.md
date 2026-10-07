# Current state — REMEMBER-KEYS delivered to main (after CROSS-RESUME)
Updated: 2026-10-07. Claude continuity, user-directed. Contract `audit/contracts/remember_keys.md`.
API keys can now be kept after the program closes: a "remember on this computer" checkbox (start,
resume and learning key fields) stores them in the Windows Credential Manager for the current user
(`key_store.py`, ctypes, no new dependency; target `ScholarlyTranslation/provider/<id>`); the server
loads them at start. A key saved without the box, or cleared, also removes the stored copy; "delete
saved keys" removes all stored copies but keeps them for the run. Header key icon: grey = no key,
gold = key available, green dot = saved on this computer (tooltip lists providers). Keys still never
reach HTTP responses, job/project files, logs, browser storage or os.environ. New
tests/test_key_store.py (HTTP with an in-memory store + a real Credential Manager round trip under
a test-only prefix, cleaned up). Help/UI README/ARCHITECTURE updated. Full offline suite 1265 OK
(1 skipped). Paid/provider calls 0. Not pushed. Header and settings panel checked in headless
Chrome (Hebrew + English) against a demo server with a fake store.
Next: restart the UI at a safe moment (the AUTO-CONTINUE-WRITABLE note below still applies), enter
the key once with the box ticked; later restarts need no key entry.

## Previous: CROSS-RESUME fix on main (after UI-POLISH)
Updated: 2026-10-07. Claude continuity, user-directed bug fix (no contract; pipeline ordering).
Symptom: the UI showed "פרק 23 מתוך 64 הושלם. בדיקה רוחבית של פרקים 15–22". Evidence: Jade City
75ec5d08 journal: window 14-21 started 07:24:57 right after chapter 22; a cross-correction answer
failed validation at 07:26; the user retried at 07:34; the resume translated chapter 23 first and
finished the window at 07:39. Cause: due windows ran only after a chapter completed, so any stop
inside or just before a due window (failed call, pause, app restart, budget) let the next chapter
go first. Fix: `cross_windows()` once before the chapter loop. New test
test_names_crossqa_integration::test_resume_finishes_a_due_window_before_the_next_chapter fails on
the old code and passes now. Full offline suite 1255 OK. Paid/provider calls 0. Not pushed.
Effect on the running job: none until the server restarts; chapter 23 is checked again in window 22-29.
Next: the pending UI restart (AUTO-CONTINUE-WRITABLE note below) also loads this fix.

## Previous: UI-POLISH delivered to main (after AUTO-CONTINUE-WRITABLE)
Updated: 2026-10-07. Claude continuity, user-directed. Contract `audit/contracts/ui_polish.md`.
Result screen: one short status line + one collapsed details box (export limitations grouped by
kind with counts, first notes, findings count, usage) instead of thousands of joined English
details. Processing view: labelled rows (stage, chapters, calls, spent/held/remaining) and a
per-model table, numbers LTR-isolated; secondary counters collapsed. Start/processing/result views
compacted; help link in the header. Header "English" button switches the main interface (saved in
localStorage `ui-language`), help page bilingual. Free-form server messages (blockers, errors,
review notes) and the learning section stay Hebrew. Full offline suite 1254 OK. Paid calls 0.
Static UI files only: a browser reload shows it; no server restart needed.
Open: English mode not checked against a live server (offline harness with real job data only);
a 1366x657 result view still needs a short scroll to the download button.
Next: user reloads the browser tab; the AUTO-CONTINUE-WRITABLE restart note below still applies.

## Previous: AUTO-CONTINUE-WRITABLE fix on main (after PREVIEW-SPEED)
Updated: 2026-10-07. Claude continuity, user-directed bug fix (contract user_decided_blocks addendum).
Symptom: the user again had to approve an unknown-outcome retry of $0.0084 although the standing
rule auto-accepts below $1. Evidence: Jade City job 75ec5d08, local-correction event 309 ended
failed_transport (not metered) at 09:38; the user settled it by hand at 09:45 (decision without
`auto`). Cause: `document_draft._auto_continue` opened controls.sqlite3 with `create=False`
(read-only); `user_settle` failed with StoreCorruptionError, caught silently, so no auto decision
and no resume. Earlier tests exercised only job_blocks with a writable store. Fix: open writable
(create=True; existence already checked). New test
test_document_draft::test_automation_disconnect_below_one_dollar_resumes_without_asking fails on the
old code and passes now. Full offline suite 1216 OK. Paid/provider calls 0. main not pushed (also
PREVIEW-SPEED). Jade City is running under the old server code.
Next: user restarts the UI at a safe moment (pause Jade City first or wait for its next stop); from
then on under-$1 unknown outcomes retry automatically (max 3 in a row).

## Previous: PREVIEW-SPEED fix delivered to main (after LEARN-GRAMMAR)
Updated: 2026-10-07. Claude continuity, user-directed bug fix (no contract; planner-internal).
Symptom: the UI showed no cost estimate and could not start a translation. Cause: planning
placeholders (notebook/bridge reserve, synthetic Hebrew targets, correction issue) were single
unbroken runs ('x' * ~66k, 'א' * n, '𐀀' * n); tiktoken's BPE is quadratic in such runs (66k Hebrew
6.4 s per count) and planning counts them hundreds of times per book, so the preview request ran
for >10 minutes with tiktoken installed (the UI runtime). The offline suite runs without tiktoken
(byte bound), which hid it. Fix: `_filler` breaks runs every 64 chars with same-UTF-8-width
whitespace (bytes, byte bounds and plans unchanged); fit checks use `upper_bound_tokens` (no
discarded fallback-encoding count). Jade City preview with tiktoken: >10 min -> 16 s. New
tests/test_planner_fillers.py; the reference planner shares the placeholder shape. Full offline
suite 1215 OK after rebasing on LEARN-GRAMMAR; planner/preview suites also OK under the tiktoken runtime. Paid/provider calls 0.
Next: restart the UI (the running server holds the old code), then the estimate appears.

## Previous: LEARN-GRAMMAR delivered to main (after ARTICLE-NOTES)
Updated: 2026-10-07. Claude continuity, user-directed. Contract `audit/contracts/learning_grammar_lesson.md`.
Learning preparations started from now on get (a) one Luna call per chapter after its chunks: a
3-5 paragraph Hebrew grammar lesson (gender, inflection, voice...) with examples grounded in the
chapter (woven insertions from accepted edits; exact chapter quotes rendered in the target
language); invalid answers -> "unavailable", book still ready; shown in reader, HTML/EPUB export
(chapter text once, lesson after it) and personal grammar files; (b) learner's-dictionary entries
(part of speech, gender, senses, labeled forms, note) inside the existing chunk call, once per
lexical item when first woven (catalog words too); progress rows open into the entry plus woven
book sentences; dictionary.json/md include them; (c) a grammar notebook view of all lessons with
search (`/learning/grammar-notebook`). User decisions: extra call per chapter, insertions + full
sentences, new preparations only, entries in the existing call, no backfill. Full offline suite
1212 OK. Paid/provider calls 0. Restart the UI to use it; jobs paused under old code continue
without lessons/entries.
Open: lesson/entry quality untested on a real book (model-written, no linguistic review);
browser rendering of the new progress/notebook views not visually checked.

## Previous: ARTICLE-NOTES delivered to main (after BOOK-VOICE)
Updated: 2026-10-07. Claude continuity, user-directed. Contract `audit/contracts/article_notes.md`.
PDF articles (digital or scanned): line geometry marks bottom-of-page footnotes (also continued
on the next page), running headers (wide gap, >= 3 pages), display-size headings and the reference
list; note marks become [^n] for translator/review/correction and are repaired in answers;
reference entries, running headers and bare formulas pass through with no call; math (x2, α3,
(3)) is never a mark. PDF export puts each note at the bottom of its mark's page (continues on
the next page when long); HTML links marks to a notes list. User decisions: notes at the page
bottom, references kept in the original, input PDF digital/scanned, mathematics considered.
New structures only (existing jobs keep their structure). Full offline suite 1192 OK.
Paid/provider calls 0; no restart.
Open: tested on a synthetic article only; the first real article should be checked by the user
(two-column layouts and per-page note numbering are not handled).

## Previous: BOOK-VOICE delivered to main (after EXPORT-NIQQUD)
Updated: 2026-10-07. Claude continuity, user-directed. Contract `audit/contracts/book_voice.md`.
The first name-table source-pass call also decides the book's register and key words (title words
included); they become global notebook entries (`voice`, `key-word`) that translator, reviewers and
keeper see; the keeper may refine them. No new calls. New jobs only (ready tables do not rerun).
Open (a) from EXPORT-NIQQUD below is resolved by this delivery.

## Previous: EXPORT-NIQQUD delivered to main (after PUNCT-RHYTHM f87addb)
Updated: 2026-10-06. Claude continuity, user-directed. Contract `audit/contracts/export_niqqud.md`.
From the Senlin Ascends job (dccf6947, completed 50/50, $1.14): EPUB export now spreads a merged
unit's translation one line per original block (no English left behind); NAMES shows plain
(unvocalized) forms unless two forms collide (Wen/Woon); prompts 07/09 ask for unvocalized
forms; cross-chapter QA drops corrections that only add niqqud. Full offline suite 1164 OK.
Paid/provider calls 0; no restart; job data untouched.
Open: (a) register/voice guidance in the name-table source pass — proposal pending user
decision; (b) niqqud already in finished Senlin/Jade City text stays until a user-started cross
check or a user-approved local cleanup; (c) chapter QA retains many MAJOR hebrew_quality notes
(Senlin 160) — no decision yet. PUNCT-RHYTHM (f87addb, concurrent session) has no audit entry.
Next: restart the UI at a safe time; re-export Senlin to get the fixed EPUB (no model calls).
