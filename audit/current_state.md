# Current state
Updated: 2026-10-05T04:55:00Z (Claude conductor)

**Pushed.** `main == origin/main == 55ae999c9c65a8954dd388879d6ca6a4e26db22c`
(verified by fetch + `git rev-parse` immediately before and after push; no
divergence). See `audit/gate_history.md`'s "SESSION-G | ... | verified push
receipt" entry. Everything below describes what that commit contains.

Phase: A/B/C/D(+persistent-state addendum)/E/F/X/EPUB-schema/G all
integrated and tested. Verified via `git fetch` + `git rev-parse HEAD
origin/main`: both equal `15426ec` -- the prior checkpoint's claim of 2
unpushed commits was stale; everything through the EPUB-schema session was
already pushed. This session's Session-G work (549 passing tests via
`python -B -m unittest discover -s tests`, run with the project's `.venv`
which has pdfplumber/reportlab/Pillow installed) is uncommitted working-tree
changes on top of `15426ec`, not yet committed or pushed.

An untracked `AUTOMATION_WORK_PLAN_HE.md` (not authored by this session)
appeared in the working tree during this session, proposing a *future*,
separate automated chapter-translation/QA-budget phase; its own text
explicitly defers to this Session G ("close the existing Session G, or get
an orderly handoff from its owner, before extending it"). Left untouched
and excluded from this session's commit -- it is not this session's file to
commit or act on.

Session G (this session) closed every item the prior checkpoint deferred to
it:
1. **Budget/cache wiring.** `document_draft.py`'s per-document budget used
   to cover translation only; `review_qa.py` review/chapter-QA calls ran
   completely unmetered and never touched the persistent
   `runtime_controls.ControlStore`. Now one shared `ControlStore` task per
   document covers translate+unit-review+chapter-qa, and
   `job["estimated_cost_usd"]` updates live from it.
2. **Output-cap-aware pricing.** The worst-case reservation and cache key
   hard-coded one global `OPENAI_MAX_OUTPUT_TOKENS` regardless of a
   resolved role's real configured `max_output_tokens`; both now use the
   actual per-task/per-call cap.
3. **Chapter QA -> persistent document state.** `review_qa.py`'s chapter
   QA now also emits a grounded, certainty-limited `STATE_UPDATES` section
   (never `established` from a model); `document_draft.py` translates
   chapter-by-chapter, commits non-conflicting proposals via
   `document_state.find_conflicts`/`commit_update`, and feeds the result
   into the next chapter's translation. Covered end-to-end by
   `tests.test_document_draft.ChapterQAPersistentStateTests` (the
   addendum's 10 named scenarios).
4. **EPUB export reconciliation.** `export_epub_from_document_structure`
   bridges the canonical schema-2 structure onto `export_epub.py`'s
   existing archive-rewriting path (positional node matching; a unit
   spanning multiple original blocks records a
   `units_merged_multiple_blocks` limitation rather than guessing a
   split). EPUB upload is no longer refused anywhere (`document_draft.py`,
   `web_ui.py`, `ui.html`/`ui.js`); real PDF->PDF and EPUB->EPUB both work,
   confirmed by a live-server HTTP smoke test in addition to unit tests.

Also added at the user's explicit request: `Run Scholarly Translation.vbs`
(double-click launcher for the existing `run-ui.ps1`, opens the browser
automatically via `web_ui.main()`'s own `webbrowser.open`) and
`install.ps1`/`Install.bat` (a simple WinForms GUI installer: creates
`.venv`, installs `requirements.txt`, verifies, creates a desktop
shortcut), documented in `INSTALL_HE.md`.

Documentation updated to be accurate rather than aspirational: README.md's
"Simple local document UI" section was describing an obsolete
`document-draft@1`/HTML-output UI; rewritten, plus new "Translation
context, chapter QA and persistent state" and "PDF/EPUB export and its
limitations" sections. `UI_README_HE.md` fully rewritten to match the
actual current flow.

**Explicitly NOT done (documented limitations, not defects left silently
unfixed):** real per-model/per-provider pricing (only OpenAI is priced at
all; unchanged from before G, now clearly documented); visual acceptance
of either exporter against real, complex documents (footnotes, tables,
formulas, mixed Hebrew-Latin) -- still only exercised by synthetic
fixtures and one live-server smoke test with trivial content. Gate-10
human quality pilot remains BLOCKED and unaffected by this session.

Exact next action: none pending for Session-G code; it is committed and
pushed. The two "Explicitly NOT done" items above require either a human
visual-acceptance pass on real documents or a user decision on
multi-provider pricing, not more unsupervised building. Whoever owns
`AUTOMATION_WORK_PLAN_HE.md` (not this session) can now proceed per its own
text, which was waiting on this Session-G checkpoint/handoff.
