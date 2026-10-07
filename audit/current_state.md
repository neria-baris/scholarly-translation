# Current state — LEARN-GRAMMAR delivered to main (after ARTICLE-NOTES)
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

## Previous: SCHOLARLY-PARITY delivered to main
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
