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

---
Previous checkpoint:
# Current state — SINGLE-INSTANCE on main (not pushed)
Updated: 2026-10-09. Claude Code primary agent (conductor), user-reported bug.

Main: 422d649 SINGLE-INSTANCE (contract audit/contracts/single_server_instance.md) on 7a06f80. Not pushed (origin/main = 7a06f80).
Cause of "נעצר" + resume -> "ההכנה כבר רצה": two web_ui servers live at once (PIDs 2864 from 15:49 on port 54376, 19368 from 16:02 on port 50756), both on outputs/learning, each with its own in-memory running set, overwriting shared state. Fix: web_ui holds an OS lock on outputs/web_ui.lock; a second launch opens the running server and exits.
Verification: full offline suite 1411 tests, 1 failure (test_server_text_en: new Hebrew console string) fixed by making the console line English; affected tests (server_text_en, single_instance, web_ui) 15 PASS. Runtime provider calls 0.
Translation + learning in parallel: supported in one server (one translation document and one learning book at a time, separate slots).

Next action: stop both old servers (they carry no lock), start one server, resume learning job session-f928b03a (124/355, failed/auto-retry); then push main if the user approves.
