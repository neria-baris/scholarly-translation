# Current state — ACCOUNT-SYNC + KEYS-IN-DIALOG + DEFAULT-ROLES on main, not pushed (Claude Code conductor, session 68, 2026-11-05)
User requests: signing in from the profile window must be enough for translation; Luna low / Sol medium by default; the key light blinks green when a key exists; API keys only in the key window, not in the translation flow; models preselected (user chose: Luna translates, Sol reviews; reasoning each model's default) and "Checked" marked recommended.
Branches feat/account-sync-defaults (54f76fd) and feat/keys-in-dialog (17be7ed, f74a351) merged with main 24870e0 and fast-forwarded into local main. Not pushed: main also carries other sessions' unpushed commits (cat swat, OCR bundle) whose checkpoints wait for the user's request before pushing.
Tests: full suite 1871 on the branch before the last main merge: only new failure test_preview_uses_real_chapters_quickly (65 s vs 60 s cap), which also fails on main c0298f6 without these changes (68 s) — a timing regression from another change, not from these. After the merge: tests/ui, models, budget, bundled-tesseract tests and headless-Chrome checks (cat, profile, keys window, default roles, account sync, key light) pass.
Next action: user restarts/uses the app; on the user's request push main (gh credential); investigate the slower long-document preview separately.

---
# Current state - OCR-BUNDLE committed, 1.0.1 release on hold (Claude Code conductor, 2026-11-05)
Tesseract 5.4.0 is now bundled (scholarly_translation/assets/tesseract/, see run_history OCR-BUNDLE). Release 1.0.1 is on hold: the user is testing the OpenAI sign-in first and will say when to publish. At release time: build from main, trial-install, attach libiconv-1.17.tar.gz and jbigkit-2.1.tar.gz (GPL/LGPL sources; URLs and SHA-256 in assets/tesseract/sources.json) to the GitHub release, then refresh the distribution README (its OCR section now says nothing to install).
Next action: wait for the user's go-ahead after the OpenAI sign-in test, then release 1.0.1 as above.
Also on main (not pushed): CAT swat. A mouse pointer within paw's reach of the sitting cat (not over him) makes him face it and swat 2-3 times; JS rotates and stretches the near front leg every frame so the paw lands on the pointer (measured 0-1 px in headless Chrome, ahead/up/low/behind; out of reach = no swat). Cooldown 3.5-6 s; roam mode only, never while moving, napping, thinking or held. tests/ui/test_ui_redesign 17 OK.

---
# Current state — sitting cat drawing fixed (Claude Code conductor, 2026-11-05)
main = the CAT commit after f9cc218, not pushed. Sitting cat (8b19c91 + follow-up at the user's request): the belly is drawn up and back off the floor (no square corner, it no longer reads as fat), only the legs touch the floor; while grooming a cream chest shows behind the lifted paw and the other front leg steps under the chest; eyes are black (#1b1410). Checked by headless Chrome renders of sit/groom/happy; tests/ui/test_ui_redesign 17 OK.
Uncommitted: only the untracked source PDF (do not commit).
Next action: user restarts the app and watches the cat groom; on the user's request, push main to origin (gh credential).

---
# Current state — tab icon + orphaned batch-parse fix committed (Claude Code conductor, session scholarly-translation-cf, 2026-11-05)
main = b531ebb on top of bee8a1f, not pushed. fb58318: the cat logo (assets/app.ico) is served at /favicon.ico and is the tab icon on all five pages and the sign-in page; the old inline SVG icon was removed (its raw '#' colours were read as a URL fragment, so it never rendered). b531ebb: the previously staged, ownerless chapter_pipeline change (context_unit_ids: drop an extra batch item for a chapter-context unit) committed at the user's request; sessions b8, 9c and 68 each said it is not theirs.
Tests: tests/ui 242, only the pre-existing Python 3.9 write_text(newline=) error. tests/translate 430 (PYTHONPATH=tests): 1 failure, test_preview_uses_real_chapters_quickly (60 s timing limit); it also fails on HEAD without the change (63.3 s), so it is a machine-speed issue, not this change.
Uncommitted: only the untracked source PDF (do not commit).
Next action: on the user's request, push main to origin (gh credential, see below); then restart the app (session 68 runs it at http://127.0.0.1:54045/) and check the cat in the tab.

---
# Current state — PROFILE-EVERYWHERE + CAT fixes merged (Claude Code conductor, 2026-11-05)
User asked for a sign-in window and a drawn profile on every screen, and for the cat to stay visible, vary its thoughts and move after too many clicks. Contract audit/contracts/profile_everywhere.md. Branches feat/profile-everywhere (builder, 6547c61) and fix/cat-visible-lines (conductor, 67e9804) integrated on feat/profile-and-cat (wording fix 623989d) and fast-forwarded into main; pushed via the gh credential.
Tests: full suite 1862, only the 33 pre-existing Python 3.9 write_text(newline=) errors. Headless Chrome (sandbox): profile button + window on all five pages at 1280/390, Esc/focus; cat visible after scrolling (roam and nap), leaves after 12 fast clicks, 8 distinct thoughts.
Coordination: session scholarly-translation-cf holds a tab-icon patch (favicon route, <link rel=icon> on every page) to rebase onto this main.
Old OpenAI card in model settings stays; the old Google header button is hidden and driven from the window. Worktrees profile-ui, cat-fix, profile-cat-integrate (and openai-*) can be removed after review.
Uncommitted, not ours (unchanged): staged translate/chapter_pipeline.py + its test; untracked source PDF.
Next action: user restarts the app and checks the profile window and the cat; the OPENAI-ACCOUNT live sign-in test below is still pending.

---
# Current state - RELEASE-DIST v1.0.0 published (Claude Code conductor, 2026-11-05)
Public distribution repo https://github.com/neria-baris/scholarly-translation-app (runtime files + bilingual README), release v1.0.0 built from dd7f95a: ScholarlyTranslation-Setup.exe, Setup.zip, signed manifest.json(.sig). Local dist checkout C:\Users\pc2\projects\scholarly-translation-app (core.autocrlf false, '* -text'); assets in C:\Users\pc2\projects\scholarly-translation-app-release-1.0.0. Release signing private key: C:\Users\pc2\.scholarly-translation-signing\release-signing.key (outside the repo; the owner must back it up - without it no further update can be published). main = merge of release/dist-v1 with OPENAI-ACCOUNT; v1.0.0 deliberately excludes OPENAI-ACCOUNT (not verified live). Dev repo main pushed to origin/main as a fast-forward after the OPENAI-ACCOUNT push (see Git).
Next release: commit on main, then from a clean checkout `python scripts/release/build_release.py --version 1.0.1 --dist-checkout C:\Users\pc2\projects\scholarly-translation-app --notes-he-file .. --notes-en-file .. --execute`, sign with the key above, commit/tag/push the dist checkout (git push via `-c credential.helper= -c "credential.helper=!gh auth git-credential"`: the stored git credential is a different account), `gh release create`. Sophos may hold a freshly built Setup.exe; gh uploaded it fine this time.
Uncommitted, not ours (unchanged): staged translate/chapter_pipeline.py + its test; untracked source PDF.
Next action: the user downloads Setup.exe from the release page on a clean Windows account (or another PC) and installs it; separately the OPENAI-ACCOUNT checkpoint below still awaits the user's live sign-in test, after which it can ship as 1.0.1.

---
# Current state — OPENAI-ACCOUNT merged (Claude Code conductor, 2026-11-05)
Sign in with an OpenAI account (official Sign in with ChatGPT + plan usage), plan budget first, API key on exhaustion by the user's visible setting. Contract audit/contracts/openai_account_sign_in.md. main = 07e0acc, pushed to origin/main 2026-11-05 (fast-forward 7a06f80..07e0acc: feat/openai-account backend 45dea7a, UI 466d065, integration 125b24c, help page 07e0acc). The GitHub repository neria-baris/scholarly-translation is PUBLIC (verified via the API); the user chose to push as-is. Push needs the gh credential (account neria-baris): git -c credential.helper= -c 'credential.helper=!gh auth git-credential' push origin main (the default Git credential is neriabaris-lang, 403). No active delegated work; worktrees .claude/worktrees/openai-backend, openai-ui, openai-integrate can be removed after review.
Tests: full suite 1846, only the 33 pre-existing Python 3.9 write_text(newline=) errors (same as e25ea47).
Not yet verified live: real OpenAI consent screen, plan-granted scope, a plan-billed call, and the fallback on a real exhaustion. Requires the user's own sign-in (ChatGPT Plus/Pro).
Uncommitted, not ours (unchanged): staged translate/chapter_pipeline.py + its test; untracked source PDF.
Next action: user restarts the app, connects the OpenAI account in model settings (allowing plan usage on the consent screen), runs one small translation; conductor checks the job record shows observed_provider openai-chatgpt-plan and actual_charge chatgpt_plan, and fixes any request field the plan route rejects.

---
# Current state — UI-LIBRARY-REDESIGN merged (Claude Code, 2026-10-15)
The library design is now the real app UI (contract audit/contracts/ui_library_redesign.md, doc docs/design/UI_LIBRARY_REDESIGN_HE.md). Branch feat/ui-library-redesign fast-forwarded into main; worktree .claude/worktrees/ui-redesign can be removed after review. Not pushed (remote unchecked). No active delegated work. Verify locally: python scripts/design/serve_ui_sandbox.py --data outputs/ux/ui-redesign/data --port 8840, then node --experimental-websocket scripts/design/verify_ui_redesign.mjs. The running app picks up the new UI after a restart.
Uncommitted, not ours (unchanged): staged translate/chapter_pipeline.py and tests/translate/test_chapter_pipeline.py; untracked source PDF.
Next action: user reviews the redesigned app after restarting it; on approval, push with the usual remote/ancestry checks.

---
# Public release — pixel library prototype (Claude Code, 2026-10-16)
User asked to publish the pixel-library prototype with its development process, publicly, on the neria-baris GitHub account. Published: https://github.com/neria-baris/pixel-library (PUBLIC), Pages https://neria-baris.github.io/pixel-library/ (built, pages 200).
Contents: only design/pixel-library, docs/design/pixel-library, scripts/design, audit/contracts/ux_*, audit/checkpoints/ux_* from design/pixel-library-prototypes 3581774, with its 19 commits rebuilt (same messages/authors/dates, new hashes; public tip 63d588d = 3581774 tree subset) + root README/index.html/.nojekyll (2df578d). Shared audit logs and all other project files excluded; scanned for secrets/local paths (none). scholarly-translation stays PRIVATE.
Future prototype updates: republish from the design branch by the same path-subset rebuild; do not push the private repo there.

---
# Current state — COMIC on real pages (Claude Code session); other owner's checkpoint below
Updated: 2026-10-15. Claude Code primary agent (conductor) for the comic work.

Comic code: scholarly_translation/comics/. Latest commit 33e624f + receipt. Not pushed.
Output: outputs/comics/torrezno-01-a2/comic.pdf = pages 1-40 (written 17:25; page 3 credits untranslated). A rerun to fix page 3 was stopped by the user mid-way; its journal holds one 'dispatched' step of unknown outcome (a rerun of that exact step is refused: use a new --notebook or run only --pages 3 into a separate folder).
Cost so far for the quarter: text ~\$2.4 + image edits ~\$4.2. For the rest of the book recommend --edit-art-text off (~\$10 for the whole book).
Uncommitted, not ours: staged/modified translate/chapter_pipeline.py, tests/translate/test_chapter_pipeline.py, untracked models/timing.py (other owner). Untracked source PDF: do not commit.
Next action: user reviews the quarter PDF; on request, translate page 3 alone (one Luna call) and/or continue with pages 41+.

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
