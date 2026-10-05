# Builder B — Hebrew EPUB and immutable translation-library import

Read LANGUAGE_LEARNING_PROMPTS_HE.md, 01_shared_contract.md, AGENTS.md and your
scoped audit/contracts/learn_1.md. Work from the same frozen bootstrap as A/C.

## Owns

New scholarly_translation/learning_import.py;
tests/test_learning_import.py with tiny synthetic EPUBs created within that test.
Existing epub_extract.py, document_draft.py, chapter_pipeline.py and job storage are
read-only references. Do not edit them, web_ui.py, UI files, shared schema, audits,
policies, requirements or another worker's files. No Git/paid calls/delegation.

## Implement

- import_hebrew_epub reuses the existing validated EPUB reader and existing
  logical structure/chapter helpers where appropriate. Preserve reading order,
  headings and paragraphs with stable IDs. A spine item isn't always a semantic
  chapter: reuse existing normalization behavior and preserve its uncertainty.
  For missing chapter structure use labelled sections, not invented chapter claims.
- Protect compressed archive/resource/path limits through the current reader.
  Copy normalized text only; never expose EPUB scripts/active HTML/external
  resources to the learning browser. No OCR, translation or PDF-upload feature here.
- Detect empty/damaged/unsupported/non-Hebrew-base text honestly; allow foreign
  names/quotations in Hebrew books. Clear code-bearing failures, no model detection.
- import_translation_job consumes the server-resolved latest completed Hebrew
  snapshot specified by Sol. Inspect actual current target/edited version format;
  preserve chapter/unit order and provenance. Reject missing target text or unfinished
  jobs; never substitute original foreign source for absent Hebrew.
- Materialize an independent immutable LearningSource. Copy title safely and
  record original job/source revision and source hash. Editing/regenerating the
  original translation later cannot mutate a previously imported learning book.
- Both paths produce the same source contract. Do not render a translated EPUB,
  export/download it and parse it again if stored Hebrew units can be copied directly.
- No state progression, active-book selection or filesystem-root choice here;
  persistence and HTTP resolution belong to A/Sol.

## Acceptance

Valid synthetic Hebrew EPUB and equivalent library snapshot produce equivalent
ordered content; malicious markup stays inert text; damaged/empty/invalid EPUB
returns clear errors; headings/chapter order stable; mixed-script Hebrew accepted;
wrong language rejected; missing Hebrew target and unfinished job rejected;
latest saved edits imported; later original edits don't mutate the independent copy.
Run only relevant offline tests; report integration not run if other workers absent.

Report changed_files, actual source adapter mapping, commands/results or not_run,
deviations, risks and observable model usage. Stop at your scoped implementation.
If existing helper cannot be reused safely without edits, report the small missing
adapter need to Sol. Do not fix existing EPUB or library code in this worktree.
