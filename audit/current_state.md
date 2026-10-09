# Current state — LEARN-SALVAGE built on branch, integration awaiting user decision
Updated: 2026-10-09. Claude Code primary agent (conductor), user-directed learning fix.

Main: 4e3979e (SYNC-VERIFY). The main checkout still holds pre-existing, unverified, uncommitted learning/runtime changes (18 files: learning model choice, Haiku catalogue entry, interrupted-call recovery, learning auto-retry, fenced-JSON tolerance, UI). They were not authored in this session and were not modified.

Branch fix/learn-salvage (worktree .claude/worktrees/learn-salvage): commit 1 = exact snapshot of those uncommitted changes (WIP-SNAPSHOT, unverified as authored); commit 2 = LEARN-SALVAGE (contract audit/contracts/learn_salvage.md). Policy@3 learning answers: spans located by original text, repeated Hebrew context trimmed, invalid parts dropped, quotas trim instead of rejecting; book notebook (learned items ranked, book-wide paced new-word allowance from local word counts) via prompt asset 13 (learning-generation@4); rejected answers resent after 2/5/15/30 s. Policy@1/@2 unchanged.

Verification: learning tests 250 PASS; full offline suite 1409 PASS (skipped=1) 476.1 s on the branch (snapshot + fix). Offline replay of recorded rejected learning answers: 11/13 accepted. Runtime provider calls 0.

Open: (1) user decides how the pre-existing uncommitted changes enter main (commit them as-is, or let their author finish) before fix/learn-salvage is integrated; (2) after integration restart the UI server so the waiting learning job (session-f928b03a, auto-retry running) uses the new code; (3) provider-side JSON schema enforcement not done (no malformed-JSON evidence). Gate-10 real-source/human quality acceptance stays pending. LEARN-EN-BASE contract at 6f70896 remains separate, unimplemented.

Active delegated work: none started in this session. Many older worktrees exist; not touched.

Next action: obtain the user's decision on the pre-existing uncommitted main changes, then fast-forward/merge fix/learn-salvage into main, re-run the full suite on main, push only as authorized.
