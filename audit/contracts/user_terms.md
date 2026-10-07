# USER-TERMS: personal glossary, binding user terms, term check

Date: 2026-10-07. Base: 7a9e833 (CJK-STRUCTURE). Claude continuity, user-directed. Branch
`feat/user-terms`.
User report: the UI document's glossary was empty, and the model rendered 無尽蔵性
(inexhaustibility) as "אי התכלות" where the user wants "אי-מיצוי". Finding: the UI flow always
starts from an empty formal glossary (`glossary.py` needs human-proposed, source-bound rules and
the UI offers none); terminology came only from model choices: the name table's 62 `term` entries
and the notebook's key words, one of which grouped 不完全性 (incompleteness) with 無尽蔵性. The user
could neither see nor correct them.

Component / owns:
- `user_glossary.py` (new, pure + atomic file I/O): terms `{source, forms, target,
  target_language, note}`; `normalize`, `load`, `save`, `for_target`, `parse_text`/`format_text`
  (UI text form `source | form = target  # note`), `occurs` (CJK substring, otherwise whole word,
  case-insensitive), `applicable`. Limits: 2000 terms, 8 forms, source 60, target 80 (name-table
  limit), note 500. Hebrew error messages (English in SERVER_EN).
- `DocumentJobs(user_glossary_path=...)`: `start` stores `job["user_terms"]`, a snapshot of the
  target language's terms; an unreadable glossary refuses the start with its message. The web
  UI keeps the file at `outputs/ui/user_glossary.json`.
- `chapter_pipeline._seed_user_terms` (when chapter plans are first made): the snapshot's terms
  that occur in the document are recorded in `job["user_terms_applied"]` and enter
  (a) the name table, origin `human`, kind `term`, before the source pass, so the add-only merge
  drops any model entry sharing one of their forms (the source pass also sees them);
  (b) the book notebook via `book_notebook.add_user_terms`: global human entries tagged
  `user-term`, rendered as "BINDING: set by the user, use exactly this rendering"; the keeper
  cannot change them; model entries sharing a source form are shadowed (not shown to the
  translator, marked "overridden by a user term" in the Markdown download).
- `_unit_findings`: each user term whose form occurs in the unit's source adds a `term_missing`
  check; `output_checks._contains_term` treats hyphen, maqaf and space alike for Hebrew.
- Web: `POST /user-glossary` and `/user-glossary-save` (`target_language`, `text`) return
  `{text, count}`; saving replaces only that target language's terms. UI: "My terms" field in the
  options (loaded per target language, saved explicitly or before translating); on the result
  screen the document's terms (user, name-table terms, notebook key words) with "Correct", which
  saves a binding term for the next translation.

Invariants: no model call; jobs without `user_terms` (all earlier jobs) behave as before; prompts
change only when a user term occurs in the document. Resumed jobs keep their start snapshot.

Acceptance: `tests/test_user_terms.py` (11 tests: text round trip and errors, persistence,
matching, binding/shadowing in the excerpt, keeper refusal, name-table precedence over the
source pass, term check with maqaf/space variants, HTTP save/load and the job snapshot). Full
suite 1336 OK. The UI was not checked in a browser in this session.

Out of scope: re-translating an existing document with new terms (a new translation run is
needed); the formal source-bound glossary; reasoning effort (user handles separately).
