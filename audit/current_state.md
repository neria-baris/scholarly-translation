# Current state — SINGLE-INSTANCE on main (not pushed)
Updated: 2026-10-09. Claude Code primary agent (conductor), user-reported bug.

Main: 422d649 SINGLE-INSTANCE (contract audit/contracts/single_server_instance.md) on 7a06f80. Not pushed (origin/main = 7a06f80).
Cause of "נעצר" + resume -> "ההכנה כבר רצה": two web_ui servers live at once (PIDs 2864 from 15:49 on port 54376, 19368 from 16:02 on port 50756), both on outputs/learning, each with its own in-memory running set, overwriting shared state. Fix: web_ui holds an OS lock on outputs/web_ui.lock; a second launch opens the running server and exits.
Verification: full offline suite 1411 tests, 1 failure (test_server_text_en: new Hebrew console string) fixed by making the console line English; affected tests (server_text_en, single_instance, web_ui) 15 PASS. Runtime provider calls 0.
Translation + learning in parallel: supported in one server (one translation document and one learning book at a time, separate slots).

Next action: stop both old servers (they carry no lock), start one server, resume learning job session-f928b03a (124/355, failed/auto-retry); then push main if the user approves.

---
Previous checkpoint:
# Current state — LEARN-SALVAGE integrated on main and pushed
Updated: 2026-10-09. Claude Code primary agent (conductor), user-directed learning fix.

Main: c5d6f88 (LEARN-SALVAGE) on 000e49c (WIP-SNAPSHOT of previously uncommitted learning/runtime changes: learning model choice, Haiku catalogue entry, interrupted-call recovery, learning auto-retry, fenced-JSON tolerance, UI; kept by user decision, authored before this session). Working tree clean. Pushed: origin/main = 84d0a76 (integration receipt) plus this push receipt.

Branch fix/learn-salvage (worktree .claude/worktrees/learn-salvage): commit 1 = exact snapshot of those uncommitted changes (WIP-SNAPSHOT, unverified as authored); commit 2 = LEARN-SALVAGE (contract audit/contracts/learn_salvage.md). Policy@3 learning answers: spans located by original text, repeated Hebrew context trimmed, invalid parts dropped, quotas trim instead of rejecting; book notebook (learned items ranked, book-wide paced new-word allowance from local word counts) via prompt asset 13 (learning-generation@4); rejected answers resent after 2/5/15/30 s. Policy@1/@2 unchanged.

Verification: learning tests 250 PASS; full offline suite 1409 PASS (skipped=1) on the branch (476.1 s) and again on main (553.8 s). Offline replay of recorded rejected learning answers: 11/13 accepted. Runtime provider calls 0.

Open: (1) restart the UI server (web_ui running since 15:49 has the old code) so the waiting learning job (session-f928b03a, auto-retry running) uses the new code; (3) provider-side JSON schema enforcement not done (no malformed-JSON evidence). Gate-10 real-source/human quality acceptance stays pending. LEARN-EN-BASE contract at 6f70896 remains separate, unimplemented.

Active delegated work: none started in this session. Many older worktrees exist; not touched.

Next action: user restarts the UI server and resumes/continues the learning job.
