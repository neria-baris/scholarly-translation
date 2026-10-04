# Current state
Updated: 2026-10-05T01:00:00+00:00 (Claude conductor)

Phase: A/B/C/D(+persistent-state addendum)/E/F(PDF-only)/X integrated,
tested and pushed. `origin/main` == `main` == `c2b6b174` ("Integrate
Session F: simple UI rewired onto canonical backend (PDF path)").
Independent full-suite rerun on merged main: 513 tests pass, 0 skips
(26.8s), bundled runtime
`C:/Users/pc2/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.

Stage summary: A=structure schema 2; B=scholarly+literary profiles;
C=optional review/chapter QA (review_qa.py); D=chapter-aware context
(context_strategy.py) + versioned cross-chapter persistent state
(document_state.py, NOT yet wired to C's chapter QA - that's G's job);
E=role-based provider/model selection; X=PDF/EPUB export (export_pdf.py
working fully; export_epub.py works for the X session's own export-only
scope but cannot yet receive a translated EPUB from the canonical
pipeline - see below); F=the simple upload/translate/download UI now
drives the real backend for PDF end-to-end (structure -> translation
-> quality-mode-gated review -> export_pdf); EPUB upload in that UI is
explicitly refused pending the decision below.

OPEN PRODUCT/ARCHITECTURE QUESTION (raised to the user, not yet decided):
Session F found that `translation.build_translation_request` transitively
requires every reading candidate to carry literal provenance
`stage == "digital-pdf@1"` plus positive `pdf_width`/`pdf_height`
(enforced in `source_reading.py` ~lines 132-162, confirmed by conductor
inspection). EPUB text has no page geometry and never goes through PDF
digital extraction, so it cannot satisfy this without either fabricating
false provenance or extending that core schema with a new non-geometric
digital-text origin type. This is a genuine cross-cutting decision
(touches source_reading.py/document_structure.py, used by segmentation.py
and translation.py) - the user has been asked to choose a path (schema
extension to support real EPUB translation vs. shipping PDF-only for now
with EPUB staying export-only/BLOCKED) before Session G runs, since G's
own completion checklist names "EPUB -> translated EPUB" as part of the
fully supported final feature set.

Original clean worktrees preserved at sibling scholarly-translation.worktrees/
(A/B/C/E, fully merged) and .claude/worktrees/ (untracked, harness-managed:
D's, X's and F's are done and may be pruned once confirmed with the user).

Quota and actual subscription charges unknown. No new external paid
model/provider calls this session (mock/fixture-only).

Exact next action: awaiting the user's decision on the EPUB-translation
schema question above. Once resolved (either via a small follow-up
contract to extend source_reading.py, or by confirming PDF-only for now),
launch Session G (final integration review), which per
audit/claude_integration_conductor.md plus the 2026-10-05 persistent-state
addendum must additionally: (1) wire Session C's chapter QA output into
Session D's document_state.py via the smallest adapter necessary; (2) add
the ten addendum test scenarios end-to-end; (3) run the complete test
suite and fix only concrete integration defects; (4) document the EPUB-
translation limitation (or its resolution) accurately.
