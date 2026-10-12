# Current state — COMIC on real pages (Claude Code session); other owner's checkpoint below
Updated: 2026-10-12. Claude Code primary agent (conductor) for the comic work.

Comic commits on main (not pushed): 839f016, f369db0, 615b3f6, 255138a, 87b5813, 1fe299c, e77cf0c (see run_history). CLI: python -m scholarly_translation.comic_pipeline INPUT --out DIR --source-language es --target he --translator openai:gpt-6-luna:medium --reviewer openai:gpt-6-luna:medium [--pages] [--mirror auto|yes|no] [--review on|off] [--notebook].
Outputs (ignored): outputs/comics/torrezno-01 (v1, pages 1-33; store has one interrupted call with unknown outcome), -v2 (pages 10-13, story context), -v3 (pages 10-13, shape + review, Luna medium; current best).
Open: user judges v3; known gaps: lettering the recognition box misses stays (mirrored), tiny text in squeezed neighbours, partial sfx restore, review trusts wrong transcriptions. Full album only on explicit user approval (user wants test runs).
Uncommitted, not ours: staged scholarly_translation/chapter_pipeline.py and tests/test_chapter_pipeline.py (other owner) — do not commit or revert. Untracked source PDF in repo root: do not commit.
Next action: wait for the user's verdict on v3 pages 10-13.

TOPIC-LAYOUT (separate Claude Code session, 2026-10-12, user request; contract audit/contracts/topic_layout.md on the branch): branch `chore/topic-layout` (worktree .claude/worktrees/topic-layout), one commit on top of main, NOT merged. Package split into core/sources/models/budget/translate/review/export/comics/learning/ui, tests mirrored; entry points `-m scholarly_translation.ui.web_ui` and `-m scholarly_translation.comics.pipeline` (the comic CLI above changes on merge). Full suite 1525 OK (baseline 1523 + 2 new comic tests). Supersedes unmerged `chore/package-layout`. Merge blockers: the running web UI (lazy imports; restart it after merge) and the other owner's staged chapter_pipeline.py/test change, which must be carried to translate/ and tests/translate/ and left staged. Next action: on user approval, stop the web UI, fast-forward main to the branch, re-apply that staged patch at the new paths, restart the UI.

---
Previous checkpoint (other owner):
# Current state (2026-10-11T15:55:24.649211+00:00)

Main code delivery ecf7c3d86dc08e83270d8517bcaa321e19b91c66, parent e035107 ROMAN-PAGES.
Other owner reconciled math changes; former Git blocker resolved. Learning work
committed; tracked tree/index clean. Pre-existing untracked .claude/ preserved.
Contracts: learn_parallel.md and learn_arabic_frontmatter.md under audit/contracts.
Concurrent languages/books, frozen opening snapshots, additive completion for
future books, Arabic MSA/native script/RTL, and immutable start-chapter setting.
Excluded initial chapters retain Hebrew in reader/exports with no model calls,
lessons, exposure, context or allowance denominator; old sessions default 0.

User UI follow-up fixed: new static files were served by older process (five
languages, chapter arrays absent). New process/current live browser now shows
Arabic and 50 chapter choices; selector expansion/selection verified, chapter 1
restored, frontend reloaded. Added notice and disabled preparation on incompatible
summary. No real preparation/translation or provider calls started by conductor;
no server killed. Old tabs should use current URL in outputs/web_ui.url.

Validation: complete learning regression279 OK129.595s; latest focused UI29
OK0.075s, HTTP12 OK8.342s, six executed Node compatibility cases and JS syntax
PASS. Previous broad credential-manager environment failures remain recorded;
no all-repository PASS claim. Conductor only; advisers/builders/runtime calls0;
subscription usage/cost not_metered. Temporary editing script removed; screenshot
is private ignored output, never stage it. Pre-existing untracked .claude/ untouched.

Git: complete/staged intended diffs reviewed; 43 paths committed. Remote
check hung and was interrupted, no accessible remote/ancestry verification; do
not push. not_synced until network restored. Next: push only after successful remote/ancestry checks. Delivery receipt
records the code hash separately; it cannot embed its own receipt hash. No additional gate
without remote-backup warning. Real-comic quality still requires real samples.

Previous checkpoint: audit/checkpoints/roman_pages_e035107.md preserves the
other conductor's exact HEAD checkpoint and its own previous checkpoint.
