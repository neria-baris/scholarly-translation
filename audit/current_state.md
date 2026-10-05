# Current state
Updated: 2026-10-05T19:30:00+00:00 (Claude continuity; LIBRARY-HTML-INSTALLER integrated)

LIBRARY-HTML-INSTALLER (contract audit/contracts/library_html_installer.md, e10ee37):
user explicitly authorized >2 parallel builders for this gate only; three disjoint
writers merged sequentially: B1 373f5a4 (export_html, html render_download,
/document-library, download format), B2 a9a78f1 (library panel UI: font choice,
PDF/EPUB/HTML downloads, reopen), B3 a56908a (installer auto-installs per-user
Python 3.12 via winget or signed python.org installer, py -3.x probing, pip upgrade,
run-ui without python39). 799 tests OK; both .ps1 parse clean; live loopback smoke
listed library and served HTML (embedded font) + PDF. Not verified: real browser
click-through of library panel; actual Python auto-install on a machine without
3.10+ (never executed by design). No provider calls. Builder worktrees preserved.
Next exact action: push and record receipt; then await user direction.


LONG-DOCS (pushed 9cc42e4) and LIT-NOTEBOOK accepted as scoped software. Budget: required
user value for paid runs, no code ceiling. New automation jobs keep a model-maintained
book notebook (free tags, chapter summaries, story so far) used by translation and QA;
legacy jobs unchanged. 760 tests OK. No active delegated work; builder branches
worktree-agent-a6bbb2ac65efc98fe / -ab9068247a6539e9e / -a7de952124f5698fb merged.
Open options for user: expose keeper role (context_state_builder) in UI; blind sample
chapter comparison (paid, needs authorization); real browser run of a configured job.
Next exact action: push and record receipt; then await user direction.

BOOK-REFERENCE-2 (user: closed book did not look like a book): sprite rebuilt to
48 frames after the reference - real closed cover/spine/label/page edges, hinge
cover swing, page-block flip, two page turns per loop, mirrored close on back cover.
ui.css offsets updated; 659 offline tests OK; Edge render + animation probe verified.
GOLD-THEME: ui.css palette moved from teal to the book gold/parchment (contrast
>=5.2:1, 659 tests OK). Pushed 3b4cdaa+0445bde; main==origin/main verified, receipt recorded.
No active delegated writer.

Verified BOOK-REFERENCE implementation d695978e93e853b464cec691ebcc32e988463aaf normally pushed.
Post-push fetch confirms main==origin/main and clean tree; separate receipt records
that hash. Prior automation implementation59a06d6 and receipt200ec77 retained.
Contract audit/contracts/book_reference_animation.md. No active delegated writer.

User supplied a gold/cream pixel book sheet. Reconstructed code-native40-frame
SVG, deterministic tools/build_book_sprite.py; fixed /book-sprite.svg asset route.
Opening0-7, page loop8-31, mirrored closing32-39; pause/error static; reduced
motion uses stable open/closed views. Actual stage/percent and all processing,
translation/QA/cost/key/font behavior unchanged. Art is reference-based recreation,
not original attachment bytes. Screenshot outputs/automation/book-reference-preview.jpg
is ignored design-only gallery with labelled example percentages.

22 existing focused HTTP tests passed (9 in7.667s,13 in8.440s). XML40-frame bounds,
full mirrored endpoints, exact regeneration and served SVG MIME/bytes verified.
Edge loop changes positions; static pause/opposite ends verified, reduced-motion
demonstration static, mobile375px no overflow. Actual completed Auto job shows new
asset100%, no console errors. Prior659 full acceptance60.956s remains; backend
only adds fixed local static route. No additional broad testing without new risk.

No external Sonnet/Opus/Astra/runtime calls this visual gate; internal Sol usage
not_metered. Prior six automation builder calls list$14.2851749, actual subscription
charge unknown, unchanged. No secrets/private source/output evidence staged.
Existing unrelated Claude worktrees and brokenold.venv preserved.
Product/ignored art-fixture loopback server50152, runtime session16878.

Core automation software remains accepted: independent models/QA, memory-only
endpoint-bound keys, token/cost preflight, reserved QA funds, durable response
reuse, safe pause/resume, stale QA after edits and five fonts with zero generation
on rerender. Gate10 remains BLOCKED on approved representative sources/references,
runtime authorization/credentials and expert judgments. Cache hits, output/expansion
and Other price assumptions uncalibrated. Partial export, auto QA after edits and
auto-dispatch on server startup not implemented; completed export/explicit resume
supported. Next: genuine pilot only with prerequisites; visual gate closed.
