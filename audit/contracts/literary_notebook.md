# LIT-NOTEBOOK — mandatory budget, rolling book notebook, sharper literary review

Authority: user, 2026-10-05. Go-to models gpt-6-luna / gpt-6.1-sol. Base: `9cc42e4`.
User decisions: (1) no code-level budget ceiling, but no paid run/preview without a
user-set positive finite budget (required field). (2) Memory must adapt to the book: a
model-maintained rolling notebook with free tags (examples, not a closed set), updated
every chapter in every quality mode, consulted by review; per-chapter plot summaries;
human review optional only (nothing ever waits for a human).

## Components and ownership
C. `scholarly_translation/book_notebook.py` + `runtime_prompts/07_book_notebook_keeper.md`
   + `tests/test_book_notebook.py` (new files only). Pure, no I/O, no provider calls.
   - Notebook `book-notebook@1`: document_id, revision, entries, chapter_summaries,
     story_so_far, history. Entry: entry_id (deterministic), tags (1-4 free strings,
     normalised, suggested list incl. wordplay/humor/quote/allusion/name/character/
     place/term/register/motif/ambiguity/style), title, note, hebrew_rendering (optional),
     match_terms (source-language strings used for retrieval), scope `global|local`,
     first/last chapter index, status active|superseded, origin model|human, pinned.
   - Keeper prompt: book-type adaptive; record only what will change how later text is
     translated or reviewed, including chosen Hebrew renderings (names, puns, idiolects,
     forms of address and gender); never pad; plot summary 3-8 sentences; story_so_far
     <= 250 words. Strict JSON ops: add/update/supersede, chapter_summary, story_so_far.
   - `apply_keeper_response(notebook, raw_text, chapter_index)` -> (notebook, report):
     validates/bounds every field, ignores bad ops with warnings, never raises on model
     output, never overrides pinned/human entries, bounded totals (entries <= 3000,
     note <= 600 chars, title <= 120, match_terms <= 12).
   - `render_for_chapter(notebook, chapter_source, token_budget)`: deterministic
     selection: pinned + global, entries whose match_terms occur in the chapter source,
     entries touched in the last 2 chapters, previous chapter summary, story_so_far;
     truncate by priority to budget. `render_markdown(notebook)` for download.
D. Budget + prompts (owns `document_draft.validate_settings` budget lines, `web_ui.py`
   budget handling, `ui.html`/`ui.js` budget field, `help.html`/`UI_README_HE.md` budget
   text, `translation_profiles.py` literary/scholarly style text, `runtime_prompts/04`,
   `06`, `semantic_review.py` risk triggers, tests in new `tests/test_lit_budget_prompts.py`).
   - Configured (paid) runs and previews require explicit `budget_usd` > 0, finite; no
     upper bound; missing/empty -> clear Hebrew error; UI field required and empty by
     default (remembered value allowed); Auto/mock mode makes no paid calls (unchanged).
   - Sharpen literary profile + chapter QA prompt to use a BOOK_NOTEBOOK section:
     consistency of names/renderings/voice/running jokes, whether wordplay/humor/
     allusions land in Hebrew, translationese/calques, Hebrew dialogue punctuation.
     Bump PROMPT_VERSIONS. Literary risk triggers (dialogue, quoted speech, likely
     wordplay markers) so risk-based review reaches literary units.
E. Integration (after C and D merge; owns `chapter_pipeline.py`, `document_draft.py`
   wiring, result UI notebook view/download): notebook replaces document_state for new
   automation jobs (legacy jobs keep document_state); render notebook into translation and
   QA prompts; keeper call after each chapter's translation and before its QA, in all
   modes; keeper role = context_state_builder if configured, else chapter_qa, else
   translator; keeper calls included in plans/preview/budget; bridge = tail of previous
   chapter (source + Hebrew, bounded) in the next chapter's prompt; journaled/resumable
   like other steps; malformed keeper output degrades to "no update" with a visible note.

## Invariants
No paid/network calls in tests. Source text never in errors/logs. Existing tests pass.
Human edits optional; no step blocks on human input. Legacy jobs resume unchanged.
Out of scope: pre-run style sheet UI, human notebook editing UI, quality claims (Gate10).
