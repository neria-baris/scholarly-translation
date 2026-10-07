# UI-POLISH — shorter result messages, one-screen layout, clear progress, English interface

Authority: user request 2026-10-07 (Claude continuity, user-directed): (a) the messages after a
translation finishes are unclear and fill the screen; (b) the page is too tall, the help link needs
scrolling, also in the translation (processing) view; (c) the progress information at the bottom of
the processing view is unclear and has an RTL problem; (d) an English interface button for English
speakers. The user asked for as many parallel builders as needed (>2 allowed for this run).

Evidence: completed Jade City job c69bb5fc has 3097 `export_limitations` (missing_translation 2607,
inline_markup_flattened 373, units_merged_multiple_blocks 117, English `detail` strings) that
`renderResult` joins into one paragraph; plus review notes, a findings line and a per-model usage
paragraph. `renderUsage` writes provider/model names and numbers into RTL paragraphs, so bidi
reorders them.

## Components and ownership (all under `scholarly_translation/`, tests under `tests/`)

- UI-STATUS (items a + c): `ui.js` functions `renderResult`, `renderUsage`, `renderProcessing`
  (detail/budget/usage part only) and new helpers they need; `ui.html` processing-panel and
  result-panel status elements (lines inside `#processing-panel` and `#result-panel`); CSS only as a
  new block appended at the END of `ui.css` (do not edit existing ui.css lines); new test file
  `tests/test_ui_status.py`; revise stale assertions in existing UI tests.
- UI-FIT (item b): existing `ui.css` rules (do not append at the very end of the file — put new
  rules right after the "Keep the main action visible" line), `ui.html` header/start-panel/footer
  (outside `#processing-panel`/`#result-panel`); new test `tests/test_ui_fit.py`.
- HELP-EN (part of item d): `help.html` only (bilingual), new test `tests/test_help_en.py`.
- UI-EN (item d, after the three above are integrated, sequential): `ui.html`, `ui.js`, `ui.css`
  for the language switch; new test `tests/test_ui_language.py`.

## Invariants (all components)

- No Python/server change, no new HTTP route, no new static file: the running UI server reads
  ui.html/ui.js/ui.css/help.html from disk per request, so a browser reload shows the change without
  a restart (Jade City job 75ec5d08 is running and must not be disturbed).
- No change to job data, API payloads, budget/decision logic or which buttons exist; every existing
  element id that ui.js uses stays (hidden or moved is fine).
- Hebrew remains the default language; existing Hebrew strings asserted by tests stay unless a test
  is revised for an intended behaviour change.
- No provider calls, no secrets, no paid actions.

## Acceptance

- (a) After completion the result card shows at most one short status line about notes by default.
  Export limitations are grouped by kind with a Hebrew explanation and a count (no per-unit list, no
  raw English detail by default); review notes, findings count and usage live inside one collapsed
  "details" element. Nothing in the result card grows with the number of units.
- (c) Processing view shows progress as labelled rows (stage, chapters, calls, spent / held /
  remaining budget) and a small per-model usage table; Latin names and numbers are isolated LTR
  (`<bdi>`/`dir="ltr"`) with thousands separators; secondary counters (cache, reasoning, local
  replays) are collapsed.
- (b) At a 1366×657 viewport the start page (options closed) shows the footer help link without
  scrolling; a help link is also reachable from the header on every view; the processing view
  (no decision box) fits the same viewport.
- (d) A header button switches the whole main interface (static text, aria labels, placeholders,
  dynamic strings built in ui.js, known fixed server stage labels/quality labels) between Hebrew and
  English, sets `<html lang dir>`, persists in localStorage key `ui-language`, and does not lose the
  current view/job. Help page shows English when `localStorage['ui-language']=='en'` or URL hash
  `#en`, with its own switch. Free-form server messages (blocker text, errors, review notes) may stay
  Hebrew (rendered `dir="auto"`); the learning section stays Hebrew.
- `node --check ui.js` OK; full offline suite OK; headless-browser screenshots of start, processing
  and result views reviewed by the conductor.

out_of_scope: server-side English messages, learning UI translation, export/limitation semantics
(why missing_translation is recorded), new features.

## Addendum — SERVER-TEXT-EN (user: "continue", 2026-10-07)

The user accepted the offered follow-up: in English mode, the Hebrew messages the Python server
writes (blocker messages and option labels, job errors, review notes, HTTP errors, stage labels)
appear in English too. Decision: client-side table `SERVER_EN` in ui.js (one entry per line),
Hebrew templates with {n} placeholders → English; `serverText()` matches exactly or by pattern and
translates captured values recursively; unknown text is shown unchanged. No Python change, so jobs
already stored (Hebrew notes in job.json) translate as well and no server restart is needed.
Guard: `tests/test_server_text_en.py` extracts every Hebrew UI template from the server modules
with `ast` and fails when one lacks an English entry (or an entry is dead), so a new server message
must be translated in the same change. Exclusions (documented in the test): linguistic word lists,
regex classes and model prompts. Out of scope: the learning section; model-written text (findings,
notebook) stays in the language the model wrote it.
