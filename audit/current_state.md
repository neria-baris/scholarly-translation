# Current state
Updated: 2026-10-05T03:00:00+00:00 (Claude conductor)

Phase: A/B/C/D(+persistent-state addendum)/E/F(PDF-only)/X/EPUB-schema
integrated and tested; not yet pushed. `main` == `f750278` ("Integrate
EPUB digital-text schema extension"); `origin/main` still at `20fa0c9`
(2 commits behind: contract d2ca2d7 + checkpoint 12ce6d3 were also not
yet pushed before this). Independent full-suite rerun on merged main:
527 tests pass, OK, bundled runtime
`C:/Users/pc2/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.

Stage summary: A=structure schema 2; B=scholarly+literary profiles;
C=optional review/chapter QA (review_qa.py); D=chapter-aware context
(context_strategy.py) + versioned cross-chapter persistent state
(document_state.py, NOT yet wired to C's chapter QA - that's G's job);
E=role-based provider/model selection; X=PDF export (export_pdf.py
working fully) + EPUB export (export_epub.py, still its own bespoke
`epub-structure@1` path, see below); F=the simple upload/translate/
download UI drives the real backend for PDF end-to-end; EPUB upload in
that UI is still explicitly refused (unchanged by this session, see
below).

RESOLVED 2026-10-05: EPUB-translation schema question. Contract
`audit/contracts/session_epub_digital_text_schema.md` (d2ca2d7) was
implemented by an isolated-worktree builder, reviewed file-by-file by
the conductor against the contract, independently retested (527 tests,
OK, matching the builder's own report), and merged (`f750278`, merging
builder commit `2278415`). Added: a new non-geometric "digital-text"
source-evidence origin in source_reading.py/document_structure.py
(branches on origin throughout; no existing PDF/OCR check relaxed) plus
a new epub_extract.py producer mirroring pdf_extract.py, reusing EPUB's
own HTML block kind (h1-h6/p/li/blockquote: h1->heading/5, h2-6->
subheading/6, p->paragraph, li->list, blockquote->quotation) instead of
classify_line heuristics. export_epub.py's archive-parsing primitives
were factored into a shared epub_archive.py (its public ExportError
contract unchanged; all 18 pre-existing export tests pass unmodified).
Confirmed by a new end-to-end test, not just asserted:
translation.py/context_strategy.py/review_qa.py/document_state.py/
glossary.py needed zero changes - build_translation_request now
succeeds for an EPUB-derived unit via the mock provider.

Still open, explicitly deferred to Session G per the contract: (1)
export_epub.py's own `epub-structure@1` extraction/export path is not
yet reconciled with this new schema-2-capable EPUB structure, so a
translated EPUB still cannot be written back out through the canonical
export path; (2) epub_extract.py is not wired into the simple-UI job
runner (document_draft.py still refuses EPUB uploads - that refusal is
unchanged and still correct until (1) is done).

Original clean worktrees preserved at sibling scholarly-translation.worktrees/
(A/B/C/E, fully merged) and .claude/worktrees/ (untracked, harness-managed:
D's, X's, F's and this session's (agent-a2d6f5c14a1853182) are done and
may be pruned once confirmed with the user).

Quota and actual subscription charges unknown. No new external paid
model/provider calls this session (mock/fixture-only).

Exact next action: push the 3 unpushed commits (d2ca2d7, 12ce6d3,
f750278) to `origin/main` as a normal verified fast-forward gate push
(no divergence expected - confirm before pushing), then launch Session G
(final integration review), which per audit/claude_integration_conductor.md
plus the 2026-10-05 persistent-state addendum must: (1) wire Session C's
chapter QA output into Session D's document_state.py via the smallest
adapter necessary; (2) add the ten addendum test scenarios end-to-end;
(3) reconcile export_epub.py with the new schema-2-capable EPUB structure
and wire epub_extract.py into the simple-UI job runner, completing real
EPUB -> translated EPUB; (4) run the complete test suite and fix only
concrete integration defects; (5) document the EPUB-translation
resolution accurately.
