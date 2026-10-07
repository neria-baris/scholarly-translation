# TARGET-LANGUAGES — target-language packs, deterministic output checks, target choice in the UI

Date: 2026-10-07. Base: 8f0e654. Claude continuity, user-directed. Branch `feat/target-languages`.
User request: write the language packs and the deterministic checks proposed in the prompt
review, then add the matching UI choice (for now Hebrew or English). Defaults chosen here (no
blocking decision): stored JSON keys keep their names (`hebrew`, `hebrew_rendering`,
`current_hebrew`, `hebrew_chapter`); prompts for another target say what they hold. Deterministic
findings are review triggers and visible notes, never automatic rewrites. Learning stays Hebrew.

Component / owns:
- `target_languages.py` + `target_languages/{he,en}.md`: a pack is metadata lines (`key: value`)
  then `## KEY` sections (fragment text, leading/trailing blank lines stripped, may be empty).
  `load(code)`, `available()`, `use(code)` (context manager, contextvar; default `he`),
  `current()`, `localize(text)` replaces `{{T:KEY}}`; a line holding only an empty token is
  dropped; an unknown key raises. Metadata: name, label_he, label_en, direction, html_lang,
  script (regex class), name_rules (`hebrew_prefixes` | `exact`), niqqud (yes|no), ratio_<src>.
- Prompts: every model-facing Hebrew mention in prompt files 04-07, 09, 10 and the prompt strings
  of translation_profiles, chapter_pipeline, review_qa, name_table, book_notebook, cross_chapter_qa
  becomes a `{{T:...}}` token localized on the template before data substitution. Invariant: with
  `he` every rendered prompt is byte-identical to 8f0e654 (snapshot of a full mock run + direct
  renders, 138 prompts).
- Validators use the pack: batch-response script check (plus: an English target identical to its
  source is rejected), passthrough rule, review_qa target-text requirement, formal_checks
  `missing_hebrew_script` (he) / `missing_target_script` (other), name_table target-form check
  and distinctness (prefix/vav rule only for `hebrew_prefixes`).
- `output_checks.py` (new, pure): per unit `length_ratio`, `sentence_count`, `copied_source_run`,
  `added_dash` (not material), `name_form_missing` (NAMES entries of kind character/person/place/
  organization whose source form occurs; prefixes, vav doubling and niqqud tolerated for he),
  `term_missing` (approved glossary target term absent). Findings carry the formal-finding keys;
  `chapter_pipeline._unit_findings` adds them, so `checked` reviews the unit and the reviewer sees
  it. UI labels for the new types.
- Settings/jobs: `target_language` (default `he`; old jobs read as `he`); non-`he` requires the
  configured model (chapter pipeline); source == target rejected (explicit or detected).
  DocumentJobs runs planning, preview, execution, salvage and exports inside `use(target)`.
- Exports: HTML/EPUB `lang`/`dir` and EPUB `dc:language` from the pack; PDF aligns LTR text left
  (already automatic for text without Hebrew).
- UI: "שפת יעד / Target language" select (עברית, אנגלית), summary, translate button, processing line and
  review-editor direction follow it; disabled to Hebrew with Auto (mock) model, with a note.

Invariants: Hebrew jobs and prompts unchanged except the new findings: they add no call (`checked`
already reviews every translatable unit, `fast` none) but add REVIEW_FOCUS lines for that unit;
planner placeholders use one target-script letter (Hebrew: unchanged); no new calls, roles or
schema versions; Gate-7/8 CLI paths and learning stay Hebrew-only.
Acceptance: snapshot identity for he; English snapshot has no "Hebrew"/niqqud/prefix rule and keeps
all output formats; unit tests for pack parsing/localize, every check (positive and negative),
validators, settings, exports, UI; a full mock English EPUB run; full offline suite green.
Out of scope: more target languages (a pack file plus a UI option), renaming stored keys,
learning, cross-unit duplicate/leakage checks, paid calls.
