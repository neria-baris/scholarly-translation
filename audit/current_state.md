# Current state
Updated: 2026-10-05T14:20:00+00:00 (Claude continuity; LONG-DOCS integrated)

LONG-DOCS accepted as scoped software (contract audit/contracts/long_documents_chapters.md):
real EPUB chapters, size fitting, adaptive unit policy, planner speed, caps 3M chars/2000
pages, persisted chapter groups for resume. 709 tests OK. Builder worktree branches
worktree-agent-a3c6d5c090eaf28ac / -a9ab1557d1719b954 merged; no active delegated work.
Open user decisions: (1) MAX_BUDGET_USD (30) - Sol 6.1 checked reserve $71.63 for a
730k novel; (2) approve literary continuity/quality contract (to be drafted).
Next exact action: on answers, adjust cap and draft/implement the literary contract.

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
