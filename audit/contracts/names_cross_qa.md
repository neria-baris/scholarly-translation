# NAMES-CROSSQA — name table, cross-chapter QA, notebook keeper fixes

Date: 2026-10-06. Base: b23a217. Requested by the user after the completed run of job
c69bb5fc (Jade City, 64 chapters). Evidence (offline, no provider calls):
- keeper made 218 `add`, 0 `update`, 0 `supersede`: excerpt lines carry no entry_id, so the
  model cannot update; duplicates hold contradicting renderings (Shae: שיי ch5/32/36 vs שֵׁאי
  ch7/17/23). Text: שיי 372× (ch31-61), שֵׁאי 258× (ch8-30, 62); never mixed inside a chapter,
  so per-chapter QA cannot see it. Wen=ון, Woon=וון collide under prefixes (לוון, שוון):
  9 Wen units and 8 Woon units read וון.
- from chapter 42 every keeper call received STORY_SO_FAR with its middle cut out and
  rewrote the story from it: the middle of the book is permanently lost.
- chapters 31, 42, 59: keeper JSON had one stray `]` after chapter_summary; `_extract_json`
  took the first inner op object, report "ok", 0 ops, no summary/story, no warning.
  Chapters 38, 45, 48: no story_so_far, no warning.
- chapter 36: keeper transport failure; user accepted worst case and "retry"; step reset to
  planned but `notebook_applied` was already set, so the keeper never ran again.
- stale note "notebook not updated after chapter 30" kept after a successful rerun.

User decisions (2026-10-06): no deterministic code that checks names/terms in the
translation (open-ended, bug-prone) and no sealed-name placeholders. Instead: a model-built
name table locked automatically (no approval pause), always given to the models; a larger
notebook; cross-chapter QA every 8 chapters with one chapter of overlap (1-8, 8-15, 15-22,
...), allowed to correct automatically; niqqud may be used in names. More than two parallel
builders are explicitly authorized by the user for this task (separate file ownership,
common base b23a217, sequential integration by the conductor).

## A. Notebook keeper (owns: book_notebook.py, runtime_prompts/07_book_notebook_keeper.md, tests/test_book_notebook.py)
- `extract_json_object(raw_text, keys)` (public): returns `(obj, repaired)` or `(None, False)`.
  Strips surrounding code fences; strict `json.loads`; on a JSONDecodeError whose position
  holds a stray `]` or `}`, delete that one character and retry (at most 4 repairs,
  `repaired=True`). Accept only a dict having at least one of `keys`. Fallback: scan `{`
  positions with `raw_decode`, accepting only a dict having one of `keys` (never an inner op).
- `apply_keeper_response`: uses `extract_json_object(raw, ("ops","chapter_summary",
  "story_so_far","names"))`; unparsed -> status "unparsed" as before. Adds warnings
  "chapter_summary missing" / "story_so_far missing" when the key is absent; report gains
  `format_repaired` (bool). Returned report also carries `names_raw`: the raw `names` value
  (list or None) for the caller (name table, section B); the notebook never stores names.
- `_entry_line(e, with_id=False)`: with_id appends ` {entry_id: <id>}`.
- `render_for_chapter(..., *, with_ids=False, keep_story=False)`: `keep_story=True` never
  shortens STORY_SO_FAR or the previous summary; entries then fill `token_budget` counted
  without the story. Default behaviour unchanged except `STORY_SHARE = 0.5`.
- `build_keeper_prompt(..., names_text="")`: new placeholder `{{NAMES_TABLE}}` ("(empty)").
  Prompt: excerpt lines end with `{entry_id: ...}` — update/supersede by that id; never add an
  entry whose subject already has one. New output field `"names"`: only names (people,
  places, organizations, titles, invented terms) that first appear in this chapter and are
  not in NAMES_TABLE, objects `{"source","aliases","hebrew","kind","gender","note"}`; the
  Hebrew form is the one this chapter uses unless it would collide; every Hebrew form must
  stay distinct from every other name, also with prefixes ו ה ב כ ל מ ש (a word starting
  with ו doubles it after a prefix: ון + ל = לוון, same as ל + וון); use niqqud when needed.
  Never repeat or change names already in NAMES_TABLE.

## B. Name table (owns new: name_table.py, runtime_prompts/09_name_table.md, tests/test_name_table.py)
Schema `name-table@1`: `{"schema","status": "pending"|"ready"|"skipped","entries":[...],
"warnings":[str]}`; entry `{"source" (<=80), "aliases" ([<=80] <=12, excludes source),
"hebrew" (<=80, contains a Hebrew letter, niqqud allowed), "kind" in character|place|
organization|title|term|other, "gender" in female|male|plural|none|unknown, "note" (<=300),
"first_chapter" (int>=0 or null), "origin" in prepass|keeper|human}`. Max 1000 entries.
- `new_table()`, `validate_table(t)` (raises `NameTableError`).
- `name_candidates(texts, language, limit=400, min_count=2, snippet_chars=160)`: `texts` in
  reading order; capitalized word sequences (hyphen/apostrophe inside allowed) for cased
  languages, else `[]`; drops a single word seen only sentence-initially whose lowercase form
  occurs in the text; returns `[{"name","count","snippet"}]` by count desc then first
  occurrence. Extraction for the model only — never a check of the translation.
- `build_prepass_prompt(candidates, profile_id, source_language)` from prompt 09
  (`{{CANDIDATES}}`, `{{PROFILE_ID}}`, `{{SOURCE_LANGUAGE}}`): choose one Hebrew form per real
  name/title/invented term, skip ordinary words, group aliases, gender, distinctness rule as
  in A (prefixes, vav doubling, niqqud allowed), established Hebrew forms for real
  people/places; output strict JSON `{"names":[...]}`.
- `parse_names(value)` -> `(entries, dropped)`; invalid items dropped, defaults kind "other",
  gender "unknown", origin set by caller. `parse_prepass_response(raw)` uses
  `book_notebook.extract_json_object(raw, ("names",))`; raises `NameTableError` when no
  object with a `names` list.
- `merge_names(table, entries, chapter_index, origin)` -> `(new_table, report)` (never
  mutates): add-only; an entry whose source/alias (casefold) equals an existing source/alias
  is ignored (existing wins); identical Hebrew (NFC) for a different source is still added and
  recorded in `report["conflicts"]` and `table["warnings"]`. report `{"added","ignored",
  "conflicts"}`.
- `render_names(table, text=None, token_budget=None, count_tokens=None)` -> "" when nothing
  applies, else a header line `NAMES (binding Hebrew forms for this book; use exactly these
  forms, Hebrew prefixes attach as usual; two different names never share a Hebrew form):`
  and one line per entry `- Shae (also: Kaul Shae, Shaelinsan) → שֵׁאי [character, female] —
  note`. With `text`: only entries whose source or an alias occurs in `text` as a whole word
  (case-sensitive). Over `token_budget`: stop and add `(... N more names omitted)`.

## C. Cross-chapter QA (owns new: cross_chapter_qa.py, runtime_prompts/10_cross_chapter_qa.md, tests/test_cross_chapter_qa.py)
- `WINDOW_CHAPTERS = 8`; `windows(n)` 0-based inclusive: (0,7),(7,14),(14,21)...; last ends
  at n-1; n<2 -> []. `window_key((s,e)) = "s-e"`.
- `build_cross_qa_prompt(chapters, names_text, notebook_text, profile)`; chapters
  `[{"index","source","hebrew"}]`, rendered 1-based. Checks across chapters only: names
  (NAMES binding; one person one form; two people never one form, prefixes considered; a name
  missing from NAMES: the earliest chapter's form wins), forms of address, titles/terms,
  recurring phrases/motifs, gender agreement of characters, continuity contradictions
  introduced by the translation, voice drift. Not single-chapter issues, no restyling. A
  wrong name/term form: Span = that exact Hebrew form, Correction = the right form, MAJOR.
  Output: `VERDICT: PASS|REVISE`, `ISSUES:` (`none` or numbered Category consistency|
  continuity / Severity / Span / Correction, one line each), `NOTES:`.
- `parse_cross_qa_response(raw, source_text, hebrew_text)` (reuses review_qa grounding and
  issue slicing) -> `{"status": "completed"|"needs_human", "verdict", "issues", "notes",
  "dropped_issues", "error"}`; same per-issue tolerance and REVISE/PASS rules as chapter QA.
- `locate_issue_units(issue, records, max_units=80)` -> `(records, reason)`, reason in
  ok|ambiguous|not_found|too_many: span in one unit's Hebrew -> that unit; in several units'
  Hebrew: consistency and len(span)<=40 -> all of them (> max_units -> too_many), else
  ambiguous; only in source: the single unit containing it, else ambiguous.
- `cross_qa_output_cap(selection)` = min(role max output or 8192, 8192).

## D. Retry reopens skipped model steps (owns: job_blocks.py, tests/test_job_blocks.py)
On `accept_and_retry`/`accept_worst_case_and_retry`, before resetting, every step being
reset (same identity/stage filter as `_reset_stuck`, statuses failed|unknown|dispatched) is
reopened by stage via `dependencies_json` inputs: `chapter-notebook` -> pop
`notebook_applied`/`qa_notebooks` for `inputs.chapter` if that chapter is not completed;
`name-table` -> set `job["name_table"]["status"]="pending"` when it is "skipped";
`cross-chapter-qa` -> pop `job["cross_qa"]["windows"][inputs.window]` when its status is
"skipped". Existing raise-cap/shorten paths keep working (also for unknown/dispatched).

## E. Cross review of an existing book (owns: document_draft.py, web_ui.py, ui.html, ui.js, help.html and their UI/HTTP tests)
- `DocumentJobs.cross_chapter_review(job_id)`: refused while any job runs or for a job
  without `book_notebook`/automation/journal; calls `chapter_pipeline.enable_cross_review(job)`
  (provided by integration; returns `{"windows": int}`), sets status "paused", stage label
  "ממתין לבדיקה רוחבית", persists, returns the job. Sends nothing.
- `/document-job` adds `cross_review_available` = `chapter_pipeline.cross_review_available(job)`.
  Route `/document-cross-review`. UI box when idle and available: explains windows of 8
  chapters with overlap, automatic consistency corrections, paid provider calls that start
  only on "continue"; button "להכין בדיקה רוחבית"; afterwards the normal resume runs it.
  Help section in `#notebook`: name table, cross-chapter QA.

## Integration (conductor; owns chapter_pipeline.py and integration tests)
New jobs initialise `name_table` (pending) and `cross_qa` `{"windows":{}}`. Before chapter 1
one `name-table` call (translator role selection rules as keeper) builds the table; failure
or budget -> status skipped + note, never fails the job. The keeper receives the full table
and its `names` are merged (origin keeper). NAMES block (matched to the text, not cut by the
notebook budget, bounded by 8000 tokens) precedes the notebook in translation contexts, QA
notebooks and unit-review notebooks. Notebook budget 60000 tokens (<=1/10 usable context);
keeper excerpt `with_ids=True, keep_story=True` (falls back to the trimmed story only when the
prompt cannot fit). Successful keeper removes that chapter's stale keeper notes. After each
chapter completes, every due window runs once (key in `cross_qa.windows`, inputs.window in
the step); material consistency/continuity issues are corrected per located unit
(`target_versions` reason `cross_chapter_correction`) and rechecked by the unit reviewer;
others are retained notes. Calls protect the remaining chapters' reserve; shortage/failure
-> window status skipped + note. `enable_cross_review(job)` / `cross_review_available(job)`
for existing notebook jobs.

Invariants: no provider call outside the normal resume; name table entries are never changed
by a model; no deterministic name/term check of the translation; prior Hebrew kept in
target_versions; budget ceilings unchanged; completed translation steps never resent.
Out of scope: sealed names, deterministic name checks, UI editing of the table, Gate10
quality claims. Acceptance: unit tests per module (positive/negative), offline replay of
the 3 broken keeper answers of c69bb5fc parses fully, integration test with mock provider
covering prepass, names in prompts, windows 1-8/8-15 and a cross correction, retry reopen;
full suite green; zero paid calls.

Addendum (2026-10-06, user decisions during integration):
- Overlap chapter decides: in window 8-15 chapter 8 (already checked in 1-8) is the REFERENCE.
  The prompt marks it authoritative (later chapters follow it; no issue whose span is only in
  it); corrections never touch its units. Same rule for the overlap of split window parts.
  The first window has no reference.
- Default model is gpt-6-luna: cost/reserve tradeoffs are judged at Luna prices, so the larger
  notebook budget (60000) stays. With pricier roles (e.g. claude-sonnet-5-5 QA, $4/M worst
  input) planning ceilings rise; one UI fixture budget was raised from $2 to $4 for that.
Integration deviations (conductor): unit reviews get only the unit's names (1000-token NAMES
budget, planned reserve 1000) instead of 8000; keeper planning reserve = notebook + names
budget (the dispatch reserves the real prompt); name-table, keeper and cross-QA output caps
are bounded by the job's shared output cap (a larger cap made the control store refuse the
call and fail the job); the keeper trim loop runs up to 32 rounds; completed books get the
entry point in the result view's notebook section (status completed shows no processing view).
Out of plan: cross-QA and name-table calls are not part of the per-chapter conservative plan;
they protect the remaining chapters' reserve and are skipped with a note on shortage.
