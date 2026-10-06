# Current state — NAMES-CROSSQA delivered to main
Updated: 2026-10-06. Claude continuity, user-directed. Contract
`audit/contracts/names_cross_qa.md` (+ integration addendum). Base f61958c (contract) on
b23a217. Feature branch `feat/names-crossqa`; main fast-forward and normal push follow the
verified commit (receipt in run_history).

Cause: completed Jade City run c69bb5fc (64/64, $0.94). Notebook keeper never updated an entry
(no entry_id shown) so contradicting renderings coexisted (Shae שיי 372×/שֵׁאי 258×, flipping
between chapters; Wen/Woon both וון under prefixes); from chapter 42 the keeper rewrote a
middle-cut story; 3 keeper answers with a stray `]` silently lost; retry after a keeper
transport failure never re-ran the keeper; stale notes.

Delivered: model-built name table before chapter 1 (locked automatically, add-only, keeper adds
new names), binding NAMES block in translator/QA/unit-review/keeper prompts; keeper sees
entry_ids and the whole story, tolerant JSON (stray closer repair), missing-field warnings;
notebook budget 60000 (story share 0.5); cross-chapter QA windows 1-8, 8-15, 15-22 … with the
overlap chapter as authoritative REFERENCE (never corrected), automatic consistency/continuity
corrections + unit recheck, prior Hebrew in target_versions; retry reopens skipped keeper/name
table/window steps; "prepare cross-chapter check" for existing books (result view or paused
view) that the normal resume runs. User decisions: no deterministic name/term checks, no
sealed names, no approval pause, niqqud allowed, Luna default, >2 parallel builders.

Verification: full offline suite 1137 tests OK, also after the final UI entry point
(388s); node --check ui.js/learning.js OK; offline replay of the 3 broken c69bb5fc keeper
answers now parses fully (repaired), 3 story-less answers now warn. Paid/provider calls 0.
No live restart; jobs untouched.

Open: Jade City has the old text (no table); the user can prepare the cross-chapter check from
its result view after restarting the UI — paid Luna calls, user-started. Senlin Ascension job
is paused at chapter 1/50 under old code: restart the UI before resuming; preparing the cross
check first gives it the name table for chapters 2-50. Cross-QA/name-table costs are not in
the per-chapter plan (protected reserve, skipped with a note on shortage). Gate10 human
quality acceptance remains BLOCKED.
Next: user restarts the UI at a safe time, then (optionally) prepares the cross check for
Senlin before resuming and for Jade City.
