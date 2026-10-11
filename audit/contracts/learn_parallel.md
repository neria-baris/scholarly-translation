# LEARN-PARALLEL — concurrent language and book learning

Authorized by user 2026-10-11. User subsequently explicitly instructed Codex to
implement directly; conductor owns implementation/tests/acceptance/audit/Git.
Base: main 2e63128. Existing
untracked .claude/ belongs to prior work and must not be staged or changed.

- Component/owns: learning state/store/service/UI and personal archive adapters.
- Input: existing schema-1 learners, sessions, prepared chunks and saved jobs.
- Output: independent active sessions, frozen starting learner snapshots and
  additive, exactly-once completion receipts; legacy records remain readable.
  Schema 1 gains optional `LearnerState.active_session_ids` and
  `BookSession.starting_learner`. Store reads migrate the legacy single slot in
  a recoverable learner/session transaction before any sibling may finish.
  `active_book_id` is retained as a compatibility pointer to the first active
  session's book; membership is governed by session IDs. Frozen snapshots have
  no active membership and must agree with the session's opening metadata.
  Public session updates cannot change/remove a pinned snapshot. The pure
  completion transition receives the remaining book pointer from the store;
  it unions accepted counts/definitions with current history. Prepared-coverage
  checks and crash-window plan reconstruction use the snapshot, not later
  shared history. Dictionary dedup is bounded to the snapshot's prior books.
- Invariants: languages have independent histories; switching language and
  starting a distinct book are allowed during existing sessions. Books started
  in one language before any intervening completion share the same opening
  baseline, including level/catalog/items/vocabulary. Each completion merges its
  accepted words/structures into the current language history for future books,
  never mutating another active book's baseline/plans/content. Any new book
  started after a completion uses the accumulated history, even with an older
  book still active. No automatic mastery or
  effort increase. Duplicate active book in a language is refused. Abandonment
  releases only its own session and contributes no words. Legacy single-active
  sessions continue after restart; completion transactions remain recoverable.
- Errors: invalid session/hash/status, duplicate activation, corrupt snapshots
  and unrelated stale writes are explicit. Relaxing revision checks must not
  permit abandoned/completed sessions to resume or complete twice.
- Side effects: local state/jobs/archive only, existing per-job budget/credential
  boundaries preserved; no paid runtime calls, no private data edits.
- Acceptance: offline tests through service/store for two languages, two same-
  language books, both completion orders, duplicate completion, pause/resume and
  restart after sibling completion, abandon one and retain sibling, next-cohort
  cumulative words after each completion, legacy loading, UI controls and multi-book progress/archive.
- Out of scope: provider/model changes, paid translation, broad server lifecycle
  changes and translation-quality claims.
- Execution bound: direct Codex implementation and deterministic verification;
  subscription usage/actual cost not_metered, no external runtime provider calls.
  Conductor reviews complete diff and
  verifies relevant tests before audit and verified commit/push.
