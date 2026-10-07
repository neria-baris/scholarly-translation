# BLOCK-DECISIONS — user-decided budget/stop blocks and in-progress jobs

Date: 2026-10-06. Base: 9898011. Requested by the user after job c69bb5fc stopped
at chapter 30/64: the book-notebook keeper response was truncated at 4096 output
tokens, the truncated call was settled `failed_held`, the task was stopped and
every later call was refused; the job was invisible in the library.

Component: runtime_controls (user resolutions), chapter_pipeline (keeper cap and
story length overrides, max-call override), new `job_blocks.py` (diagnosis and
decision application), document_draft (decide/in-progress/partial download),
web_ui routes, ui.html/ui.js/ui.css (library tabs, decision box).

Owns:
- Keeper output default cap 4096 -> 16384 (still bounded by role max output and
  usable context / 3). Job override `settings.keeper_output_cap`; story length
  override `settings.notebook_story_words` (default: no word cap; the keeper keeps
  every thread; stored bound 60000 chars; excerpt budget 24000 tokens; an oversized
  story is middle-trimmed in the excerpt, never dropped).
- ControlStore user actions, each append-only audited, never silent:
  `user_settle(task_id, event_id)` turns an `uncertain` reservation into
  `settled` at its observed list estimate when usage is known, else at its full
  held (worst-case) reservation; `user_resume(task_id)` clears the stop flag when
  no reservation is uncertain; `user_raise_limits(task_id, max_calls=, hard_list_usd=)`
  only increases and refingerprints the task policy.
- Journal `reset_for_retry(identity)`: failed/unknown/dispatched -> planned only
  on an explicit user decision; the previous error is kept and the prior raw
  response is copied into job `retry_history` before reset.
- Diagnosis `blocker(job, store, journal)` -> None or
  {kind, message, options[{id, label, value?, input?}], details}. Kinds:
  notebook_truncated, failed_call, unknown_outcome, over_cap_anomaly,
  call_limit, budget_limit. Options: raise_notebook_cap, shorten_notebook,
  skip_notebook_chapter, accept_and_retry, accept_worst_case_and_retry,
  acknowledge, raise_calls, raise_budget.
- UI: library tabs "מוכנים" and "בתהליך עבודה"; in-progress entries show
  progress, spend, blocker and partial PDF/EPUB/HTML downloads; opening an entry
  shows the processing panel with a decision box; deciding applies the choice
  and resumes (missing memory-only keys still requested as before).

Invariants:
- No provider call happens as part of a decision; resume is the only sender.
- A decision never lowers spend, budget or call counts and never deletes events.
- Uncertain/anomaly states still stop automatically; only a user decision
  releases them. Integrity checks accept `user_settled`/`user_resumed` events.
- Partial downloads are labelled partial; untranslated units stay in source text.
- Completed steps are never resent; changing keeper cap/story length affects
  only not-yet-completed keeper steps.

Errors: decisions on an active, completed or unblocked job, unknown option,
non-increasing values or values above existing validation limits are refused.
Out of scope: changing automatic stop policy, billing truth, quality claims,
Gate10, partial export of non-automation jobs.
Acceptance: unit tests for each store action and integrity, diagnosis per kind,
decision application, keeper override, in-progress listing and partial
download; offline replay of the real stuck job copy reaches the keeper call
with the raised cap after the decision; full suite green.

## Addendum AUTO-UNDER-1USD (2026-10-06, user-directed)
The user set a standing rule: an `unknown_outcome` block whose total held charge
is below $1 is accepted at its held worst case and retried without asking
(`job_blocks.auto_decision`, applied by `document_draft._auto_continue` right
after a run stops, then the normal resume sends). At most 3 automatic retries in
a row (a row breaks once another call is reserved); $1 or more, a 4th repeat, and
every other block kind still wait for the user. Auto decisions are recorded in
job `decisions` with `auto: true`; store events remain `user_settled`.

### Fix AUTO-CONTINUE-WRITABLE (2026-10-07, user report)
`_auto_continue` opened the control store read-only (`create=False` means `mode=ro`), so
settling the held charge failed with `StoreCorruptionError`, which was swallowed: the rule
never applied and every under-$1 unknown outcome still asked the user (Jade City, event 309,
$0.0084, 2026-10-07 09:38). It now opens the existing store writable, like `decide`. New
manager-level test drives a real disconnect through `_auto_continue` to completion.

### Addendum AUTO-RETRY-UNDER-DOLLAR (2026-10-07, user-directed)
User report: still asked after the writable fix (academic PDF 18da9456: three automatic retries
of one semantic-reviewer call within 4 s during a network outage, the 4th failure in 0.03 s hit
the 3-in-a-row limit; the same prompt succeeded 3 minutes later). The rule now reads the user's
"under $1" literally: automatic while the charges accepted automatically in the current row plus
the held charge stay below $1 (backstop: 10 in a row). Each automatic resend waits 15 s, 60 s,
120 s, then 300 s; meanwhile the job is `paused` with a stage note and no decision box, and the
user may resume at once or pause (a user pause, manual resume or new decision cancels the timer).
Adapters also resend, like an explicit rejection, a call whose connection never opened (httpx
ConnectError/ConnectTimeout under the SDK error): nothing reached the provider. Transport errors
now name the exception classes in the step error.
