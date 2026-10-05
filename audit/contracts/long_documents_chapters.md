# LONG-DOCS — real chapters, size safety and planner scale

Authority: user, 2026-10-05 ("implement all layers"; whole-book-as-one-chapter is severe).
Base: `558a16c`. Conductor: Claude (continuity). Builders: A (input/chapters), B (planner).

Evidence (local, no calls): broken EPUB (0-byte chapters, empty spine, third-party
Ebook-lib output) -> "no spine chapters". Valid 49-file novel, 730k chars -> 150k cap;
cap lifted: one chapter group of 134 units/730k chars (EPUB never yields part/chapter
nodes), units up to 11.7k chars (2000 words) exceed 8k-output models, preview >10 min
whole-book and 289 s even per spine file.

## Layers and ownership
1. EPUB diagnosis (A: `epub_archive.py`, `epub_extract.py`): distinct errors for
   empty spine, all-empty chapter files, DRM, missing/non-XHTML items; fallback when the
   spine is empty but content exists: NCX/nav reading order, else manifest XHTML order,
   with a document warning. Hebrew actionable messages mapped in `document_draft.py`.
2. Structural chapters (A: `document_draft.py`): pure `chapter_groups(structure, units)`.
   Chapter/part nodes keep current behaviour. EPUB: each spine document is a boundary;
   documents under `MIN_CHAPTER_CHARS` merge forward (last merges backward). PDF with no
   chapter nodes: single run (layer 3 bounds it). Deterministic; never empty groups.
3. Size safety (B: `chapter_pipeline.py`): `fit_chapter_groups(structure, glossary, groups,
   configuration, quality, profile)` splits a group exceeding `MAX_CHAPTER_SOURCE_CHARS`
   or the roles' usable context into balanced contiguous parts at unit boundaries,
   preferring heading/node boundaries. Never merges groups, never reorders.
4. Unit size (B: policy; A: plumbing): `unit_policy_for(configuration)` returns `None`
   when the default 2000-word unit fits the translator output cap (default structures stay
   byte-identical), else `{"max_unit_words": w}` with a conservative chars/word ceiling.
   `extract_structure(path, language, unit_policy=None)` passes it to segmentation.
5. Limits (A): `MAX_SOURCE_CHARS` 3,000,000, `MAX_PAGES` 2,000 (sanity, memory/time);
   budget ceiling a single constant `MAX_BUDGET_USD` (value unchanged pending user);
   help/README text updated. Real gate = cost preflight vs budget + per-call fit.
6. Planner speed (B): per-unit token upper bounds computed once; packing uses an additive
   upper bound with explicit join slack, then one exact verification of each chosen
   group (shrink on failure). Estimates never lower than the exact count of the sent
   prompt. Target: 800k-char 50-chapter synthetic book preview < 15 s per quality mode.
7. Tests: each builder adds focused tests in new files; conductor adds end-to-end.

## Integration (conductor, sequential)
Wire 2+3+4 into preview, automation start and legacy path. Persist `job["chapter_groups"]`
(unit-id lists) with the plans; resume uses persisted groups; legacy jobs reconstruct
groups from `chapter_plans` batch unit ids; never regroup an in-progress job.

## Invariants
No provider/network calls in tests; mock adapters only. Source text never in errors or
logs. Journal/cache keys for unchanged inputs unchanged. Existing 659 tests pass.
Out of scope: literary continuity/quality controls (separate contract), UI redesign,
model choice, real paid runs, Gate10 quality acceptance.
