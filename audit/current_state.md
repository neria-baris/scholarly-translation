# Current state
Updated: 2026-10-05T00:20:00+00:00 (Claude conductor)

Phase: A/B/C/D(+persistent-state addendum)/E/X all integrated, tested and
pushed. `origin/main` == `main` == `9506352` ("Integrate Session X:
PDF/EPUB format-preserving export"). Independent full-suite rerun on
merged main: 509 tests pass, 0 skips (29.2s), bundled runtime
`C:/Users/pc2/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe`.

A = document structure/segmentation schema 2. B = scholarly+literary
profiles (Gate 12). C = optional review/chapter QA
(scholarly_translation/review_qa.py, chapter QA at lines ~593-761,
verdict/issues/chapter_level_notes, categories {completeness, consistency,
continuity, hebrew_quality}). D = (1) chapter-aware, model-budget
translation context strategy (context_strategy.py), (2) per the user's
2026-10-05 addendum, a versioned, source-backed cross-chapter persistent
document-state store (document_state.py: propose_item/find_conflicts/
commit_update, certainty established/likely/unresolved, model-authored
items barred from "established", document_state_version in cache key).
E = role-based provider/model selection. X = PDF export (export_pdf.py,
reportlab + a small documented Hebrew/RTL bidi routine since no rlbidi
package is installed) and EPUB export (export_epub.py, using the EPUB's
own XHTML structure as ground truth under a new epub-structure@1 schema,
since no canonical document_structure producer exists yet for EPUB).

IMPORTANT for Session G (not yet launched), per the addendum
(audit/raw/addendum_2026-10-05_persistent_state.md, contract
audit/contracts/session_d2_persistent_document_state.md): document_state.py
is deliberately NOT wired to review_qa.py's chapter QA output yet. G must
connect them with the smallest clean adapter (extending review_qa.py's
structured output only if required, never rewriting it), add the ten
addendum test scenarios end-to-end, and confirm historical reproducibility
across a state-version bump. G should also check export_epub.py's new
epub-structure@1 schema is clearly documented as EPUB-specific (not
confused with document_structure schema 2) as part of its cross-component
consistency check.

Original clean worktrees preserved at sibling scholarly-translation.worktrees/
(A/B/C/E, fully merged, kept per no-unnecessary-cleanup policy) and
.claude/worktrees/ (untracked, harness-managed: both D's and X's are done
and may be pruned once confirmed with the user).

Quota and actual subscription charges unknown. No new external paid
model/provider calls this session (mock/fixture-only).

Exact next action: launch F (simple UI integration) per
audit/claude_integration_conductor.md, wiring Academic/Literary profile
selection, Auto/explicit model choice, Fast/Checked/Thorough quality
modes, and the new export_pdf/export_epub output into the existing simple
upload/download UI (web_ui.py/ui.html/ui.js) without exposing internal
pipeline/provenance/cache details. Then G (final integration review,
including the Session C/D persistent-state wiring above).
