# REVIEW-SUGGESTIONS — apply review suggestions automatically; idiomatic translation

Date: 2026-10-10. Base: 6055666. Requested by the user: the reviewers' suggested corrections
are good and should be applied automatically, also in books already translated ("at least the
Hebrew-quality ones; consistency less"); the translator must avoid over-literal renderings.
Supersedes for chapter/unit corrections the user decision of 2026-10-06 (review_effect.md),
which applied chapter-QA issues only for consistency/continuity.

Component / owns:
A. chapter_pipeline
- `_applies_automatically(issue)`: every unit-review issue (any severity); chapter-QA
  `hebrew_quality` at any severity; chapter-QA consistency/continuity at CRITICAL/MAJOR (as before).
  Chapter-QA completeness and MINOR consistency/continuity stay retained notes.
  `_corrects_automatically` (cross-chapter QA rule) is unchanged.
- `_chapter_issue_plan(job, key, records, chapter)`: pure. Locates each issue on the text the reviews
  saw (`target_versions[0]`, else current). Per unit, the issues to send are the applicable ones
  not yet sent (`record['applied_issues']`, issue fingerprints) whose span the current text (or
  source, for QA spans) still holds; a human-edited unit gets none. Legacy records
  (`correction_done` without `applied_issues`) count the old rule's issues as sent.
- Correction loop: one bounded correction call per unit per round with all pending issues, then the
  focused recheck; `applied_issues` records what was sent. Each issue is sent at most once, so an
  existing unit gets at most one further round. Oversized payload: issues marked sent, unit unresolved.
- Budget quote counts a correction and recheck for units with pending issues; `future` excludes
  chapters already completed.
- `review_suggestions(job)` / `enable_review_suggestions(job)`: count / reopen finished chapters with
  unapplied suggestions (no provider call); a completed job becomes paused; the user's resume runs
  the corrections (paid calls). review_salvage counts units to correct with the same plan.
B. document_draft/web_ui/ui: `/document-apply-suggestions`; a box on the result and processing
  panels shows the count and prepares the run; "Resume" sends.
C. Prompts: both style profiles (scholarly v2@6, literary v2@5) get an idiomatic-structure rule;
  the Hebrew pack adds Hebrew-specific guidance (`IDIOM_NOTE`; empty in other packs); the unit
  reviewer flags over-literal structure as a MINOR issue.

Invariants: no provider call while preparing; prior text kept in `target_versions`; human edits never
overwritten automatically; completed translation steps never resent; budget ceilings unchanged.
Errors: preparing on a running, non-automation or fast-quality job is refused.
Out of scope: re-reviewing finished books with the new reviewer prompt; cross-chapter QA rule.
