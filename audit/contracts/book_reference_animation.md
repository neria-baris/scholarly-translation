# BOOK-REFERENCE — reference-based pixel book animation

Authority: user-supplied book sprite sheet, 2026-10-05 follow-up.
Owner: Sol; small deterministic UI change, no external builder required.
Owns: book SVG sprite/generator, fixed static route, existing book HTML/CSS.
Input: visible reference palette/shapes and existing job phase/actual percentage.
Output: locally generated 48-frame SVG strip (amended BOOK-REFERENCE-2: cover
swing + page-block flip 0-11, page-turn loop 12-35, mirrored closing 36-47);
static pause/error/reduced-motion. Percentage remains actual job progress.
Invariants: original stable pixel grid, cream pages/gold covers, right-opening
closed start and mirrored left-opening closed finish. No external assets, runtime
model calls, dependency, credentials or translation/QA/ledger changes. Reference
is inspiration; manually reconstructed code-native art, not original image bytes.
Errors: missing bundled asset is a deployment failure; no arbitrary filesystem route.
Side effects: existing local page loads one bundled asset; no document change.
Acceptance: deterministic regeneration, XML/frame bounds and mirrored ends;
existing focused HTTP tests; browser phase/mobile/reduced-motion inspection,
saved screenshot; reviewed clean commit/normal push plus separate audit receipt.
Out of scope: changing translation behavior, progress estimates, paid quality pilot.
