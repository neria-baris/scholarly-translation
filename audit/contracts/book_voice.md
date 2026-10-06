# BOOK-VOICE — register and key words from the first source-pass step

Date: 2026-10-06. Base: ae25fa4. Claude continuity, user-directed. Branch `feat/book-voice`.
Cause: Senlin Ascends (dccf6947): the title "Senlin Ascends" became "סנלין עולה" and chapter QA
argued over its sense; many retained MAJOR hebrew_quality notes concern register. User proposal:
the name-table pass should also grasp the book's register and set it from the start (e.g. the
title verb: נסיקה / טיפוס). User approved the recommendation (no approval pause, visible in the
notebook, keeper may refine).

Component / owns:
- `name_table.py`: `build_source_pass_prompt(..., ask_voice=False)`; with `ask_voice` the prompt adds
  a profile-specific VOICE task and asks for an optional `"voice"` field in the same JSON object:
  `{"register": str, "key_words": [{"source", "forms", "hebrew", "note"}]}`. `parse_voice(raw)`
  returns a cleaned, bounded voice dict or None; never raises.
- `book_notebook.py`: `add_voice_entries(notebook, voice, chapter_index=0)` -> `(new_nb, report)`:
  one global entry (tag `voice`) holding the register, and one global entry per key word (tag
  `key-word`, hebrew_rendering, match_terms = source forms). Ordinary keeper `add` semantics
  (same title updates), origin model, not pinned. Never mutates input, never raises on model data.
- `chapter_pipeline.py`: the first source-pass chunk (chunk 0) asks for voice; its parsed voice is
  added to the job notebook after the names merge. A missing or broken voice changes nothing else.

Invariants: no new steps, calls, roles, budgets or schema versions; other chunks' prompts are
unchanged; names parsing unchanged; failure of voice never fails or skips the name table.
Side effects: chunk-0 prompt (cache key) changes for new jobs. Existing jobs whose name table is
ready do not rerun it. Acceptance: unit tests (prompt with/without voice, parse_voice bounds and
garbage, notebook entries and dedup, pipeline chunk 0 adds entries, chunk >0 does not ask);
full offline suite green. Out of scope: UI changes (entries show in the existing notebook view),
re-running voice for finished books.
