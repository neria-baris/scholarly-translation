# Current state
Updated: 2026-10-06 | BLOCK-DECISIONS integrated (Claude continuity, user-directed)

BLOCK-DECISIONS (contract audit/contracts/user_decided_blocks.md, base 9898011):
user job c69bb5fc stopped at chapter 30/64 because the book-notebook keeper output
was truncated at 4096 tokens; settle() held the call as uncertain and stopped the
task; the job was invisible in the library. Implemented:
- Keeper default output cap 4096 -> 16384 (bounded by role max output and usable
  context / 3). story_so_far has no word cap by default: the keeper is told to keep
  every plot line/subplot and compress instead of dropping; stored safety bound
  60000 chars (warned); notebook context budget 6000 -> 24000 tokens; an oversized
  story is middle-trimmed in the excerpt, never dropped. Job overrides
  keeper_output_cap and notebook_story_words (user "shorten" = 300 words).
- ControlStore user actions (append-only events): user_settle (observed usage, else
  held worst case), user_resume, user_raise_limits (increase only). Integrity check
  takes the latest settlement per reservation; anomaly stops until user_resumed.
- Journal reset_for_retry (explicit decision only; prior raw kept in job retry_history).
- job_blocks.diagnose/apply_decision: notebook_truncated (raise cap / shorten story to 300 words /
  skip chapter), failed_call, unknown_outcome, over_cap_anomaly, stopped, call_limit,
  budget_limit. Decisions never send; resume is the only sender.
- UI: library tabs "מוכנים" / "בתהליך עבודה"; in-progress entries with progress,
  spend, blocker, partial PDF/EPUB/HTML download; decision box in processing panel
  that applies the choice then resumes.
Evidence: 816 offline tests OK; offline replay of a copy of c69bb5fc reaches the
chapter-30 keeper call with cap 16384 after raise_notebook_cap; live loopback smoke
on a copy lists it in progress (29/64 chapters, 213/378 units, $0.2244), offers the
three notebook options and serves partial EPUB/HTML. Not verified: real browser
click-through of the new tab/decision box. No provider calls.

LIMITS-RELAX (user audit request): notebook chapter summary 1200 -> 5000 chars,
entry note 600 -> 2000, rendering 200 -> 600, match terms 12 -> 24, all clips now
warned; prompt asks for complete chapter summaries; chapter bridge 1200 -> 4000
chars. Provider adapters resend automatically only after an explicit unprocessed
rejection (HTTP 429/500/502/503/504/529 before any output; backoff 2/8/20 s,
Retry-After <= 60 s honoured); connection errors, timeouts and mid-stream
failures still become user decisions. Targeted suites OK (not full suite).

LIBRARY-DELETE + HELP: library entries (both tabs) can be deleted permanently after
a confirm prompt (POST /document-delete requires confirm:true; refused while that
job runs; removes only that job folder). help.html gains Library, "When translation
stops" (decision table, automatic-resend policy) and Book-notebook sections.
Batch parser accepts stray closers/code fence after a complete array (59122a4).

Earlier today: b56df6b and 9898011 fixed untranslatable (URL-only) units blocking
translation and review. Side project LEARN-PROMPTS/WORDLISTS delivered separately
(f675162, 5a46350); user asked to keep it out of this product line of work.

Gate10 remains blocked on genuine sources/references, runtime authorization and
expert judgments. Existing unrelated builder worktrees and outputs preserved.

Next exact action: user restarts the UI, opens Library -> "בתהליך עבודה", chooses an
option for Jade City and resumes; then await user direction.
