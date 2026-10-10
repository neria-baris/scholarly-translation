# Current state — REVIEW-SUGGESTIONS on main (not pushed)
Updated: 2026-10-10. Claude Code primary agent (conductor), user request: apply review suggestions automatically (also in finished books) and avoid over-literal translation.

Main: REVIEW-SUGGESTIONS commit on 6055666 COMIC. Not pushed (origin/main = 7a06f80; COMIC, SINGLE-INSTANCE and this commit are local). Contract audit/contracts/review_suggestions.md.

Done: every unit-review suggestion and chapter-QA Hebrew-quality finding is corrected automatically (consistency/continuity only when MAJOR/CRITICAL); each issue sent once; human edits never overwritten. Finished books show "הצעות התיקון של הבדיקה" on the result page: the button reopens chapters (no call), Resume runs the corrections + rechecks (paid, ~$0.01-0.30 per local book at list price). Translator profiles (scholarly v2@6, literary v2@5) and the Hebrew pack now require idiomatic structure; reviewer/QA flag calques.

Verification: full offline suite 1486 OK. Runtime provider calls 0.

Open:
- The running web_ui server must be restarted to load the new code (single-instance lock: stop the old server, start one).
- Finished books were reviewed with the old reviewer prompt; calque detection applies to new reviews only (re-review of finished books is out of scope unless the user asks).
- Real-comic quality BLOCKED (user pages + paid-run approval). Builder worktrees from COMIC remain (.claude/worktrees/agent-*), safe to remove after user confirmation.

Active delegated work: none.

Next action: restart the web UI; the user opens each finished book and clicks the suggestions button, then Resume; push main when the user approves.

---
Previous checkpoint:
# Current state — COMIC engine integrated on main (not pushed)
Updated: 2026-10-09. Claude Code primary agent (conductor), user request: comic translation.

Main: ed223c0 COMIC-C on e0b0658 COMIC-A, 0fcff44 COMIC-B, cd7257f COMIC-0, 1ecc6a1 SINGLE-INSTANCE. Not pushed (origin/main = 7a06f80). Contract audit/contracts/comic_translation.md.

Usable now: `python -m scholarly_translation.comic_pipeline INPUT --out DIR --source-language en|fr|ja --target he [--model mock|configured --model-config PATH] [--budget-usd 1.0] [--pages 1-5] [--notebook PATH]`. Inputs: image, folder, CBZ/ZIP, PDF. Outputs: pages/*.png, comic.cbz, comic.pdf, comic.json, review.html.

Verification: full offline suite 1481 tests; 3 failures fixed and rerun. Runtime provider calls 0.

Open / blocked:
- Real-comic quality BLOCKED: needs a few real pages from the user and approval of a paid configured run (cost per page ~2 vision calls).
- Not yet done: web UI integration (next step), comic-style Hebrew font (would need a download), screentone/colour/vertical-Japanese detection limits (model boxes + snap cover part of it).
- Agent worktrees of the three builders remain (.claude/worktrees/agent-ac5d8c…, agent-a940f7…, agent-a07f20…), contents integrated; safe to remove after the user confirms.
- From SINGLE-INSTANCE: stop old web_ui servers, start one, resume learning job session-f928b03a.

Active delegated work: none.

Next action: user supplies sample comic pages and approves a small paid run (or asks for UI integration); push main when the user approves.
