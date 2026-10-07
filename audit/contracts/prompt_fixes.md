# PROMPT-FIXES — contradictions and gaps in the runtime prompts

Date: 2026-10-07. Base: 02ba32c. Claude continuity, user-directed. Branch `feat/prompt-fixes`.
Cause: a review of every runtime prompt (user request) found instructions that contradict each
other or the parsers. User decisions: fix the existing prompts first (language packs later);
narrow the dash rule to the em/en dash as added punctuation (hyphen inside words/ranges allowed;
dialogue keeps the source's marking).

Component / owns (prompt text only unless stated):
- `translation_profiles.py`: both style profiles open as guidelines (translator follows them,
  reviewers judge by them) instead of "You are translating"; one explicit order of authority
  (approved terminology and NAMES binding; BOOK_NOTEBOOK unless the source requires otherwise;
  SOURCE_CONTEXT / PREVIOUS_PASSAGE only for disambiguation/continuity); narrowed dash rule;
  literary dialogue keeps the source's marking. The single-unit footer applies glossary/decisions
  as binding and ignores instruction-like text inside data. Versions: scholarly v2@5, literary v2@4.
- `chapter_pipeline.py`: batch prefix no longer labels the guidelines "never instructions"; the
  data label moves onto SOURCE_UNITS. Review transport asks for spans as decoded text. Correction
  prompt: change only what the issues require, keep the rest character-identical, names/terms
  unchanged unless an issue concerns them, no added em/en dash. Notebook-mode chapter QA replaces
  the persistent-state section with the one-line `STATE_UPDATES: none` rule.
- `review_qa.py`: chapter-QA contract maps every check section to an allowed category, defines an
  omission span/correction, and states VERDICT = REVISE iff ISSUES is not none (parser rule);
  `ground_span` also accepts a span copied with JSON escapes (\" \\ \n).
- Prompts 04, 05, 06, 10: narrowed dash rule; 04 checks departures from glossary/NAMES/notebook
  (not "inconsistency" inside one unit) and states the verdict rule; 05 output placeholder
  `<candidate id or NO_CLEAR_WINNER>`; 10 states the verdict rule.
- `07` keeper / `book_notebook.py`: title/note/summaries written in Hebrew (as existing notebooks
  already are); chapter index line also gives the 1-based chapter number.
- `name_table.py`: the VOICE task states the output object shape with `voice`.
- Learning: `learning_generation._load_instructions` takes each section up to the next `## `
  heading (v3 no longer sends its output schema twice; v1/v2 text unchanged byte for byte);
  `10_learning_open_vocabulary.md` typos and "exactly these fields" vs dictionary add-on;
  `12_learning_dictionary_entries.md` says the field joins the same object. v1/v2 assets frozen.

Invariants: no new calls, roles, budgets, schemas or parsers' acceptance narrowed; planner
sizing still uses the same prompt builders (reserves stay >= actual); unchanged output formats.
Review/learning prompt IDs stay (their assembled text is hashed into cache/input keys).
Side effects: prompt hashes/cache keys change for new calls; resumed jobs re-dispatch only calls
not yet completed. Fixed prompt overhead grows ~50-100 tokens (one tight-context test fixture,
QA 13000 -> 13500, widened as in PUNCT-RHYTHM). Acceptance: updated prompt tests; new tests for the loader (single schema,
v1/v2 identical), ground_span escapes, prefix wording, notebook-mode QA section, dash rule text;
full offline suite green. Out of scope: deterministic output checks, language packs, Gate-8
critic/corrector JSON prompts, NAMES inside the correction prompt (changes planner reserves).
