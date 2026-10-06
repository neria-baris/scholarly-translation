# Current state — SCHOLARLY-PARITY delivered to main (after NAMES-CROSSQA + SOURCE-PASS)
Updated: 2026-10-06. Claude continuity, user-directed. Contract `audit/contracts/scholarly_parity.md`.
The fiction-oriented context work now also fits scholarly books: name-table prompt and
cross-chapter QA checks are profile-specific (scholarly: cited authors/works, key terms with
inflection, definitions, cross-references, notation, attribution, authorial voice); keeper's
literary-only rules moved to the literary guidance; scholarly translator follows BOOK_NOTEBOOK
(scholarly-prompts-v2@3); name kinds person/work; 04/06 and UI/help copy updated. Prompts only:
no new steps or calls. Full offline suite 1151 OK. Paid/provider calls 0; no restart.
Next: unchanged from below (restart the UI at a safe time; running servers predate this too).

## Previous: NAMES-CROSSQA + SOURCE-PASS delivered to main
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

SOURCE-PASS (addendum 2, same day, user report): the name table is now built by reading the
whole ORIGINAL book in chunks of consecutive chapters (<=300000 tokens of source each; Jade City:
4 calls, chapters 1-16/17-33/34-49/50-64, <= $0.14 input at Luna list price), each chunk seeing the
names so far; progress persists per chunk. A completed cross check can run again (history kept;
unchanged windows replay). Result view shows a visible cross-check box (was hidden in the
collapsed notebook section); UI/help copy states original-vs-translation. Running UI servers
(several instances, latest started 15:11) predate both deliveries: restart required to see it.
