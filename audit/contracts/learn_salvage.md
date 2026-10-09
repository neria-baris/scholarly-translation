# LEARN-SALVAGE — tolerant learning answers and a book notebook

User-directed, 2026-10-09. Evidence: 26 recorded learning calls (outputs/learning, read-only),
12 rejected; 10 for wrong character offsets (`original_mismatch`/`span`) although every
quoted `original` existed in its unit; 47% of all returned edits had a miscounted offset.
One rejection each for `foreign_share` (5-word contents chunk), `invalid_id` (local ref
`local-más`). No transport, truncation or malformed-JSON failure. All-or-nothing validation
plus 15/60/120/300 s retry waits produced the reported "ניסיון 4 מתוך 10" stalls.

- component: `learning_generation.parse_response`/`build_request` (policy@3), new pure
  `book_notebook`/`new_foreign_words`; `learning_service` notebook wiring and retry pacing;
  prompt asset `runtime_prompts/13_learning_book_notebook.md` (learning-generation@4).
- owns: span resolution, per-edit salvage, book-level new-word budget, notebook prompt section.
- input: plan (policy@3), effective catalog, optional notebook dict
  `{book_words, words_through_passage, new_foreign_words_used, new_foreign_word_allowance, learned[]}`.
- output: unchanged GeneratedChunk/recap shapes; optional caller `report` dict receives
  `dropped` reasons. Chunk warnings unchanged (reader-visible).
- invariants: source text outside accepted replacements unchanged; every accepted edit has
  `text[start:end] == original` on whole-word boundaries; accepted ids/forms/grammar grounding
  as before; known (learned) items never spend new-word budget; definitions only from used,
  valid proposals; policy@1/@2 parsing and prompts unchanged.
- span: exact offsets kept when they match; otherwise the nearest free whole-word occurrence of
  `original` in the same unit (none -> edit dropped). Empty `original` (insertion) dropped.
- salvage (policy@3): an invalid edit, invalid/duplicate proposal, invalid local ref
  (any 1-128 char string is a local alias), bad warning or malformed recap entry is dropped,
  not fatal. Quotas (new items, new grammar, new-word budget) trim edits in answer order.
  Whole answer rejected only for empty/non-JSON/not-object, wrong version/plan_id, edits not a
  list, or when it proposed edits and none survived for non-quota reasons.
- budget: `max_foreign_share` applies to the book: allowance =
  share x min(book_words, max(words_through_passage, 200)) - new words already used, floor 0.
  Words are counted locally from frozen plans (no model call). Without a notebook the old
  per-passage share is used, trimming instead of rejecting.
- notebook: learned items (projected learner, ranked by exposure, max 150) with lemma, sense,
  forms; usable as known items in any passage. Used new words persist per job.
- retry: a rejected (`invalid_generation`) answer is resent after 2/5/15/30 s; other failures keep
  the shared 15/60/120/300 s pacing. Cost/streak stop rules unchanged.
- errors: LearningError codes as before plus `no_valid_edit`.
- side_effects: none beyond job state field `new_foreign_words_used`.
- acceptance: recorded failing answers (offset cases) re-validate into accepted chunks;
  unit tests for resolution, salvage, budget and notebook; learning suite passes.
- out_of_scope: provider-side JSON schema enforcement (no malformed-JSON evidence), UI changes,
  lesson parsing, translation pipeline.
