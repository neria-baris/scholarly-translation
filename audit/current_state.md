# Current state — COMIC on real pages (Claude Code session); other owner's checkpoint below
Updated: 2026-10-15. Claude Code primary agent (conductor) for the comic work.

Comic code: scholarly_translation/comics/ (pipeline, model, review, edit, detect, typeset, records). Latest commit c89a15d + receipt. Not pushed. Recommended CLI: python -m scholarly_translation.comics.pipeline INPUT --out DIR --source-language es --target he --translator openai:gpt-6-luna:medium --reviewer openai:gpt-6-luna:medium --recognizer openai:gpt-6.1-sol:medium --review-unit page [--edit-art-text on for sound effects] [--pages] [--notebook].
Current best output: outputs/comics/torrezno-01-a2 (pages 10-13): balloons separated by words, signs kept in the original with footnotes, sound effects re-lettered. Its budget ledger shows ~\$2.6 mostly from unmetered failures during an OpenAI outage (2026-10-12 14:32-15:33).
Open: user decides on a full-album run (estimate ~\$8 without sfx image edits, ~\$13 with; Luna-only ~\$2); Haiku not cheaper (no Anthropic key saved). Known gaps: leftover lettering touching outlines; sfx labels; recogniser merging adjacent signs.
TIME-ESTIMATE (same session): the document preview shows an estimated time (expected, low-high range) beside the cost; models/timing.py holds per-model speed and the output share calibrated 2026-10-15 on 8 completed local jobs (7 inside the range). Fast/thorough and non-Luna models are uncalibrated.
Uncommitted, not ours: staged translate/chapter_pipeline.py + tests/translate/test_chapter_pipeline.py (other owner). Untracked source PDF in repo root: do not commit.
Next action: user's choice of configuration and approval for the full album (157 pages).

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
