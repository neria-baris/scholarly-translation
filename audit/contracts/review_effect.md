# REVIEW-EFFECT — unblock, grounded review that actually corrects, notebook context

Date: 2026-10-06. Base: 05748c8. Requested by the user after job c69bb5fc stopped at
chapter 52/64 and an audit of that run (51 chapters, $0.48 list):
- chapter-translate response held all 5 units but lacked the closing `]`;
- "send again" replayed the same broken response from the runtime cache (event 869, cache_hit);
- 140/267 unit reviews and 47/51 chapter QA results were discarded: spans wrapped in
  quotes/backticks (exact 7/436 and 99/411; after unwrapping 356 and 351), self-retracting
  free text inside ISSUES, one STATE_UPDATES `established`; only 4 corrections ran;
- proper_name_candidate (16,909 findings) made every unit "risky";
- late chapters saw 3-4 of 177 notebook entries (story/summary consumed the budget; 151
  entries `global`); keeper prompts wrote 568k cache tokens and read none.
User decisions (2026-10-06): chapter QA corrects automatically only consistency/continuity;
"checked" reviews every translatable unit except tiny headings; salvage chapters 1-51 of
c69bb5fc; improve keeper/reviewer/QA prompts (cache reuse, notebook size, coordination).

Component / owns:
A. UNBLOCK (commit 1)
- chapter_pipeline `_loads_json_array`: a top-level array whose only defect is a missing final
  `]` after a complete object is accepted; batch coverage/order/Hebrew checks are unchanged.
- runtime_controls `ControlStore.user_evict_cache(task_id, stage, prompt_hash)`: deletes the
  cache rows recorded for that task/stage/prompt and appends a `user_cache_evicted` event
  (actual `no_provider_call`). job_blocks `accept_and_retry` evicts for steps whose preserved
  response failed validation, so the resend really reaches the provider.
B. REVIEW-EFFECT (commit 2)
- review_qa span grounding: exact match first, else strip matching wrapper pairs
  (" “” „” ״ ' ‘’ ` « ») and a final period, repeatedly; the stored span is the grounded one.
  Applies to unit source/translation spans, chapter QA spans, STATE_UPDATES spans.
- Per-issue tolerance: an issue that cannot be grounded, is followed by stray text, has a
  non-allowlisted category/severity, or whose correction equals its span is dropped and counted
  (`dropped_issues`); STATE_UPDATES lines that are malformed/`established` are dropped and
  counted. VERDICT missing, no parseable section, or REVISE with every issue dropped stays
  `needs_human` as before.
- Corrections: unit-review CRITICAL/MAJOR as before; chapter QA CRITICAL/MAJOR only for
  `consistency`/`continuity`; other QA issues are retained notes.
- Review policy: quality `checked` and `thorough` review every translatable unit; `checked`
  skips units of at most 3 words (headings), which chapter QA still sees. Unit review output
  cap grows with unit length (bounded by the role maximum).
- formal_checks proper_name_candidate is no longer a review trigger, no longer makes
  `quality_status` draft_with_exceptions, and is stored once per token per unit.
- Prompts: reviewer/QA spans are bare verbatim single-line substrings; one line per field;
  decide before writing, never retract or comment inside ISSUES; do not report a correction
  identical to the current text; follow BOOK_NOTEBOOK renderings unless the source contradicts.
  Unit reviewer receives the notebook entries relevant to its unit. In notebook jobs chapter QA
  writes `STATE_UPDATES: none` (the notebook is the persistent state).
- Notebook: excerpt priority pinned > entries matching the chapter > story/summary (at most
  40% of the budget) > other globals > recent; keeper prompt keeps `global` for facts needed in
  most chapters, concise notes; keeper prompt reuses the chapter's cached source prefix
  (same transport as reviewers).
- Salvage: `job_blocks`/document action `recheck_saved_reviews` re-parses preserved review and
  QA responses of completed chapters with the current parser (no provider call), replaces the
  stored results/exceptions and reopens chapters with new material issues so the normal resume
  runs bounded corrections and focused rechecks (new provider calls, user-started).

Invariants: no provider call during a decision or re-parse; completed translation steps are
never resent; a dropped issue never becomes a correction; prior Hebrew kept in target_versions;
cache eviction and salvage are audited and never lower spend or counts; budget ceilings unchanged.
Errors: salvage on a running/non-automation job or a job without preserved responses is refused.
Out of scope: segmentation changes, structured-output transport, budget estimate display,
Gate10 quality claims.
Acceptance: tests per parser rule (positive/negative), eviction leads to a real dispatch,
QA category routing, review policy, notebook excerpt priority, keeper cache transport,
salvage re-parse and reopen; offline replay of a copy of c69bb5fc: chapter 48 validates from the
saved response without a call; salvage counts reported; full suite green.

Addendum (2026-10-06, user-approved "layer 1"): the batch translation parser replaces
the per-symptom tolerances (stray closers, missing final `]`) with one rule. Strict JSON
first; otherwise the answer is read as a stream of complete JSON objects, skipping only
brackets, commas, stray `}` and code fences around or between them. Free text between
items or an object cut off before its end still fails; coverage/order/duplicate/Hebrew/
formula checks decide validity. Every accepted answer that needed this is counted once
in job `format_repairs` (also for local corrections). Provider-enforced structured
output ("layer 2") is out of scope until model support is verified in documentation.

Addendum (2026-10-06, user-requested "reuse-recheck"): job c69bb5fc still needed ~12 user
decisions for 6 failures after FORMAT-TOLERANCE. Causes, from its journal and an offline
replay of a copy: (a) the block showed the oldest failed step (chapter 48, group 51, valid
under new code but reached only after reopened groups 39-50) instead of the step that had
stopped the run; "reuse" therefore re-checked nothing, and "send again" reset/evicted every
failed step of the shown stage; (b) reuse was offered even when the current code had just
rejected that answer; (c) local corrections added `"approved":false`, an empty note, or
text before the array.
- The block shows the most recently failed step; a re-check that still fails re-marks the
  step (it is the one that stopped the run). `accept_and_retry` on a failed call resets
  and evicts only that step; other saved answers stay for their re-check.
- The journal records which package-code fingerprint (`VALIDATOR_CODE`, taken at process
  start) rejected a saved answer (`meta` key `rejected_by:<identity>`, no schema change);
  reuse is offered only when that differs from the running code or is unknown.
- Batch parser: text before the answer is skipped when everything from an array start
  `[{` to the end reads as complete items (earliest such start); trailing text and
  truncation still fail. A boolean `approved` is dropped; an empty note reads as null.
  Each counts as a format repair. The correction prompt is unchanged (step identities
  of completed corrections must not change).
Acceptance: parser positive/negative tests, block shows/resets the stopping step, reuse
offered only after a code change, full suite green; all 8 saved completed answers of
c69bb5fc rejected today validate under the new code without a call.
