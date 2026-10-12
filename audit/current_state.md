# Current state — COMIC on real pages (Claude Code session); other owner's checkpoint below
Updated: 2026-10-12. Claude Code primary agent (conductor) for the comic work.

Comic code: scholarly_translation/comics/ (pipeline, model, review, edit, detect, typeset, records). Latest commits up to cf9ac94 + receipt. Not pushed. CLI adds --review-unit, --recheck, --edit-art-text (alias --edit-signs), --edit-budget-usd, --edit-quality.
Best current output: outputs/comics/torrezno-01-v4 (pages 10-13, all features; comic.pdf, review.html); signs-only check: outputs/comics/torrezno-01-v3/signs-test/013.png.
Open: recogniser box accuracy in crowded panels (Luna medium) misplaces some regions (art edits then land in the wrong place); tiny adjacent balloons overflow into each other; leftover lettering touching outlines. Options for the user: stronger recognition model (gpt-6.1-sol) or a per-page placement-verification call. Full album only on explicit approval.
Uncommitted, not ours: staged translate/chapter_pipeline.py + tests/translate/test_chapter_pipeline.py (other owner). Untracked source PDF in repo root: do not commit.
Next action: user chooses how to fix placement (stronger recogniser vs placement check).

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
