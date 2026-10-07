# LEARN-EN-BASE — language learning from an English book; learning window in English

Date: 2026-10-07. Base: 477e51e. Claude continuity, user-directed. Branches
`feat/learn-en-base` (backend, A) and `feat/learn-ui-en` (learning window, B).
User decisions (2026-10-07): an English book can be the base; glosses, senses, grammar
explanations, dictionary entries and the grammar lesson are in English for it; the learning
window and its help follow the main window's `ui-language` switch (independent of the book);
the same five learning languages (fr/de/es/yi/it); progress stays one learner per learning
language, shared by Hebrew and English books.

Component A / owns: `learning_*.py`, `runtime_prompts/10..12`, `target_languages/{he,en}.md`
(new `LEARN_*` sections only), `web_ui.py` learning routes, `ui.js` (SERVER_EN line and library
"send to learning" only), tests `tests/test_learning_*` / new `tests/test_learning_english_base.py`.
- Base language: `source.base_language` optional, `"en"` only (absent = Hebrew, all stored
  sources unchanged). Import detects it: Hebrew share >= 0.3 -> he (unchanged); else English
  when Latin letters dominate and common English function words are >= 12% of word tokens;
  otherwise `wrong_language`. New origin kind `english_epub`; translation-library imports of
  completed English jobs (settings.target_language `en`) get `base_language: "en"`.
- Plans of an English book carry optional `base_language: "en"`; Hebrew plans and plan IDs are
  unchanged. Prompts 10 (current generation), 11 (lesson) and 12 (dictionary) use `{{T:LEARN_*}}`
  tokens from the packs, localized with the book's base before data substitution; with `he` every
  learning prompt is byte-identical to 477e51e. Prompt versions of English calls get `+base-en`.
  Legacy prompts 08/09 stay Hebrew-only (an English book always uses the current policy).
- Stored field names stay (`sense_he`, `gloss_he`, `explanation_he`, `senses_he`, `label_he`,
  `notes_he`, `text_he`, `heading_he`, `note_he`, example `hebrew`); for an English book they hold
  English. Validators check the base script (Hebrew letters for he as before; Latin letters for
  en) for senses, dictionary senses/labels and lesson text.
- Planner occurrence check for an English book: case-insensitive whole-word sense match, no
  Hebrew prefix letters; Hebrew unchanged.
- Shared learner: one learner per learning language. A definition's ID hashes its sense, so a
  word defined from an English book is a separate item from the same word defined in Hebrew;
  counts, level, completed books, dictionary and grammar notebook are shared. Review of an item
  happens in books whose text matches its sense (in practice books of its definition language).
- Display/export: reader chunk/recap HTML, inline glosses, HTML/EPUB export (lang, dir,
  page-progression, labels such as chapter recap / word notes / TOC / limitation note) and the
  preserved-EPUB notes follow the book's base (English labels and LTR for an English book).
  Personal archive Markdown headings stay Hebrew (out of scope).
- API (consumed by B): `books[].base_language`, `reader.base_language`,
  `grammar_notebook.books[].base_language` (`"he"`|`"en"`); progress rows keep `hebrew` (the
  item's sense in its definition language); all error codes unchanged. Upload error text
  mentions Hebrew or English EPUB (SERVER_EN updated in the same change).

Component B / owns: `learning.html`, `learning.js`, `learning.css`, `learning_help.html`,
`tests/test_learning_ui.py` (+ a new UI test file if needed). No server/Python changes.
- Interface language from `localStorage['ui-language']` (`en` -> English, else Hebrew), read at
  load (no switch button needed in the learning window; it follows the main window); `html`
  lang/dir set accordingly. Every visible string, aria-label, placeholder, error-code message,
  status/progress text and confirmation in learning.js/html has an English version.
- Book content direction follows `base_language` (reader container, recap, grammar notebook,
  book titles with dir=auto); free text whose language is unknown (progress `hebrew`, glosses,
  explanations) uses dir=auto. Upload copy says Hebrew or English EPUB.
- `learning_help.html` bilingual like `help.html` (English via `#en` or saved `ui-language`),
  describing English books as a base.

Invariants: Hebrew books, prompts, plan IDs, cache identities, stored records and exports
unchanged; no new calls, roles, schema versions or stored-field renames; no paid calls in
build or tests; both components compile and test independently against this contract.
Errors: `wrong_language` (neither Hebrew nor English), all existing codes unchanged.
Acceptance: A — snapshot identity of rendered Hebrew prompts 10/11/12 vs 477e51e; English
import (EPUB + English library job) positive/negative (French EPUB rejected); English prompt has
no Hebrew instruction text; validators accept English and reject Hebrew senses for en (and vice
versa); mock English preparation end-to-end (plans -> chunks -> lesson -> reader -> HTML/EPUB
export LTR with English labels); full offline suite green. B — static checks that every
data-i18n key has an English entry, error codes map in both languages, help bilingual; headless
browser check of the learning window in English and Hebrew if available.
Merge order: A then B (B rebased if needed). Out of scope: Hebrew as a learning language,
more base languages, archive Markdown in English, renaming stored keys, paid calls.
