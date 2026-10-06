# Current state
Updated: 2026-10-06 | REVIEW-EFFECT integrated (Claude continuity, user-directed)

REVIEW-EFFECT (contract audit/contracts/review_effect.md, base 05748c8). Audit of job
c69bb5fc (Jade City, stopped at chapter 52/64, $0.48 list for 51 chapters) found:
the chapter-48 translation held all units but lacked the final `]`; "send again"
replayed the cached broken answer; 140/267 unit reviews and 47/51 chapter QA results
were discarded (quoted spans, self-retracting text, one bad STATE_UPDATES line), so
only 4 corrections ran; proper_name_candidate (16,909) made every unit "risky"; late
chapters saw 3-4 of 177 notebook entries; keeper prompts wrote cache and never read it.
- Commit 1 (UNBLOCK, da6beb2): missing final `]` accepted (coverage checks unchanged);
  ControlStore.user_evict_cache (audited) used by accept_and_retry after a validation
  failure so the resend reaches the provider.
- Commit 2: span grounding (quote/backtick/period unwrapping), per-issue drop+count
  instead of failing the whole answer; chapter QA auto-corrects only consistency/
  continuity (user decision); `checked` reviews every translatable unit except <=3-word
  headings (user decision); unit-review cap grows with unit length; proper names no
  longer trigger review or exceptions and are stored once per token; reviewer sees the
  notebook entries matching its unit; notebook-job QA writes STATE_UPDATES none;
  notebook excerpt: matching entries before other globals, story <=40% (keeper sees
  all); keeper reads the chapter from the translation's cached prefix; prompts 04/06/07
  tightened (verbatim spans, no retractions, notebook coordination, fewer/shorter
  global entries). Salvage: review_salvage + POST /document-recheck-reviews + button
  in the processing panel re-read saved answers (no call) and reopen changed chapters.
- Commit 3 (FORMAT-TOLERANCE, addendum): batch parser reads complete JSON objects and
  skips punctuation slips between them (one rule replacing per-symptom patches);
  accepted repairs counted in job format_repairs. Real chapter-48 answer: 5/5 units.
Evidence: 863 offline tests OK. Offline replay on copies of c69bb5fc: chapter 48
validates from the saved answer with no provider call; salvage recovers 133/140 unit
reviews and 47/47 QA results (7 still human, 186 issues dropped), reopens 51 chapters,
~112 units to correct; resume replays chapters 1-2 without calls and the next call is a
local correction. No provider calls. Not verified: browser click-through of the new
button. Known limit: reopening early chapters reserves later chapters' full planned
ceilings; with a tight budget this can surface the existing budget decision.

Earlier today (integrated): BLOCK-DECISIONS (user-decided stops, in-progress library),
LIMITS-RELAX, SCANNED-OCR (05748c8), SCHOLARLY-MATH (367d07f), LIBRARY-DELETE + help.
Side project LEARN-PROMPTS/WORDLISTS stays out of this product line.

Gate10 remains blocked on genuine sources/references, runtime authorization and
expert judgments. Existing unrelated builder worktrees and outputs preserved.

Next exact action: user restarts the UI, opens Jade City (בתהליך עבודה), clicks
"לבדוק אותן מחדש", then "להמשיך עם התשובה השמורה" (resumes: corrections for
chapters 1-51, then chapter 52 onward); then await user direction.
