# Current state
Updated: 2026-10-05T02:00:00+00:00 (Claude conductor)

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

RESOLVED 2026-10-05T02:00:00+00:00: user chose to extend the schema (not
ship PDF-only). Contract `audit/contracts/session_epub_digital_text_schema.md`
(commit d2ca2d7) defines the precise, bounded fix: a new non-geometric
"digital-text" source-evidence origin in source_reading.py/
document_structure.py (branches on origin throughout; never relaxes
existing PDF/OCR checks) plus a new epub_extract.py producer mirroring
pdf_extract.py, reusing EPUB's own HTML block kind (h1-h6/p/li/blockquote)
instead of re-deriving structure via classify_line heuristics. Design
expectation (to be proven, not assumed, by the builder's tests):
translation.py/context_strategy.py/review_qa.py/document_state.py/
glossary.py need zero changes, since they already consume the generic
schema-2 structure dict. Explicitly deferred to Session G: reconciling
export_epub.py's existing bespoke `epub-structure@1` export path with this
new schema-2-capable EPUB structure, and wiring epub_extract.py into the
simple-UI job runner (document_draft.py currently still refuses EPUB
uploads - that refusal stays in place for this session).

A builder sub-agent is being launched now in an isolated worktree to
implement this contract (tests included); it will commit to its own
branch only, not merge. Conductor reviews the diff, reruns the full suite,
integrates into main, and records an integration receipt once it reports
back.

Original clean worktrees preserved at sibling scholarly-translation.worktrees/
(A/B/C/E, fully merged) and .claude/worktrees/ (untracked, harness-managed:
D's, X's and F's are done and may be pruned once confirmed with the user).

Quota and actual subscription charges unknown. No new external paid
model/provider calls this session (mock/fixture-only).

Exact next action: integrate the EPUB digital-text schema builder's result
once it reports (review diff, rerun full suite, merge, commit integration
receipt, update this checkpoint). Then launch Session G (final integration
review), which per audit/claude_integration_conductor.md plus the
2026-10-05 persistent-state addendum must additionally: (1) wire Session
C's chapter QA output into Session D's document_state.py via the smallest
adapter necessary; (2) add the ten addendum test scenarios end-to-end;
(3) reconcile export_epub.py with the new schema-2-capable EPUB structure
and wire epub_extract.py into the simple-UI job runner; (4) run the
complete test suite and fix only concrete integration defects; (5)
document the EPUB-translation resolution accurately.
