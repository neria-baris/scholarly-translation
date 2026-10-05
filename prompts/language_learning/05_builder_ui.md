# Builder D — separate learning window and translation-library bridge

Start ONLY after A/B/C and Sol's learning HTTP service have been integrated and
verified. Read LANGUAGE_LEARNING_PROMPTS_HE.md, 01_shared_contract.md, AGENTS.md,
audit/contracts/learn_3.md and actual server routes/examples. No concurrent writer
may touch the existing UI. Use the conductor-provided integrated base.

## Owns

New scholarly_translation/learning.html, learning.js, learning.css;
edits to scholarly_translation/ui.html, ui.js, ui.css ONLY for learning entry/link
and the per-library-item transfer action; tests/test_learning_ui.py;
new LEARNING_README_HE.md. Existing web_ui.py/service code read-only.
No audit/policy/provider/schema/Git/paid calls/delegation. If API is incompatible,
report it to Sol rather than writing a parallel backend.

## Product flow

- Fully separate browser window/tab at /learning with own root/layout/script/CSS,
  opened from a simple "למידת שפה" entry in the current application. Prefer a new
  window when browser permits, with explicit link fallback if popups blocked.
  It is not another panel within the translation screen. Same local server/token.
- On every eligible completed translation-library entry, "העבר ללמידת שפה" sends
  protected POST with job_id only, then opens/focuses the learning window at that
  imported book. Do not transfer through downloads or put book text in URL/query.
  Async popup rules handled; show failure clearly without duplicate import actions.
- Learning window has "העלאת EPUB בעברית", queued/active/completed books,
  visible supported language, current effort/support, next-book settings and a
  short summary of accumulated words/grammar. Unsupported languages disabled or
  labelled honestly. User's list languages are fr/de/es/yi/it; show French as the
  proposed first working slice until other catalogs exist. A frequency-list file
  alone is not runtime language support. Yiddish text is RTL and needs explicit
  foreign-item highlighting despite sharing Hebrew script; don't infer language
  from script or remove its combining marks.
- Imported book becomes prepared only after explicit "הכן לקריאה", current
  credentials/authorization and user-supplied positive budget. Show cost/status,
  failure/resume behavior from verified backend. No generation on open/import.
  Reuse existing simple model/key setup or a link to it; don't store credentials
  in browser storage or introduce a model-role control panel.
- Reading: Hebrew base, foreign items with click/keyboard-accessible Hebrew gloss,
  chapter navigation and end-of-chapter recap. No quiz, review/QA settings or
  language-quality approval workflow. Keep content stable on rerender/reopen.
- "קראתי" is a prominent completed-preparation action. It submits the expected
  prepared hash and stable completion_id. Disable while pending; on timeout query
  state/reuse the same ID rather than inventing a fresh completion. Display the
  carried effort/items after receipt and allow next queued book to prepare from it.
  No completion event on close, scroll end, download or window opening.
- One active book per language: explain queued books and the need to finish current
  book before preparing another. Previously completed text remains readable.
- No account system or learning telemetry. Follow existing gold/parchment design,
  readable Hebrew, mixed direction, keyboard focus and narrow-screen behavior.

## Acceptance

Offline UI contract tests plus conductor real browser check: separate window and
popup fallback, library transfer, upload, safe text rendering, gloss by keyboard,
recap, explicit completion, repeat click/timeouts, next-book full continuity and
restart reopen. Existing translation/library/font/download flows still work.
Do not present static-text checks as proof of browser behavior.

Return changed_files, route bindings, commands/results or not_run, browser work
remaining for Sol, deviations/risks and observable model usage. Stop at scope.
