# COMIC — comic page translation (detect, recognise, translate in context, typeset in place)

Authority: user request 2026-10-09 ("plan, then build a comic translation project: detect the
text in the balloons, translate it, keep the context from the picture, and place the
translation precisely inside"). New capability beside the document pipeline; it reuses the
model adapters, controlled/journaled calls, budget store, target-language packs, Hebrew
fonts and bidi line reordering. Base: main 1ecc6a1 + COMIC-0 (this contract,
`comic_records.py`, `tests/comic_fixtures.py`).

## Runtime flow (per page)

```
page image (PNG/JPEG, folder, CBZ/ZIP, PDF page via pypdfium2)
 -> local detection (comic_detect): text-ink boxes + balloon interiors, no model
 -> recognition call (vision, one per page): the page with numbered marks on the local
    candidates; the model transcribes each mark, drops false marks, adds missed text with a
    box, gives kind, reading order, speaker, speaker/addressee gender, page summary,
    characters  -> regions = source evidence (never translated here)
 -> reconcile: marked regions keep local geometry; model-only boxes are snapped to a balloon
 -> translation call (vision, one per page): the clean page image + ordered regions with
    speakers/genders + capacity hint per region + the comic notebook (characters, fixed
    names, terms) + summaries of the previous pages  -> one translation per region,
    notebook updates, page summary
 -> typeset (comic_typeset): fit each translation into its region; regions that do not fit
    at the minimum size go to at most one shorten call per page, then are set at the
    minimum size with warning `overflow`
 -> render: erase the original lettering inside the region, draw the translation
 -> outputs: translated PNG per page, CBZ, PDF, comic.json, review.html
```

Context from the picture is carried three ways: the image itself goes to both calls; the
recognition record keeps speaker and genders (Hebrew verbs/adjectives depend on them); the
notebook keeps names and genders fixed across pages and, optionally, across volumes.

## Shared data spine (COMIC-0, conductor) — `scholarly_translation/comic_records.py`

Schema `COMIC_SCHEMA = 1`. Coordinates are original-image pixels, boxes `[x0, y0, x1, y1]`
with x1/y1 exclusive. Records are plain dicts validated by `validate_*`; derived data never
overwrites source (translation and layout are separate keys of a region).

- Candidate (detection output): `bbox` (union of text ink), `interior` (`None` or
  `{"step": int, "rows": [[y, x0, x1], ...]}`: one light span per sampled row, rows ascending,
  spans covering the balloon interior that holds the text), `background` `[r, g, b]`,
  `plain_background` bool, `line_height` px (median source glyph line height),
  `confidence` 0..1.
- Region: candidate geometry plus `region_id` (`p{page:03d}-r{n:02d}`), `page_id`, `order`,
  `kind` (`speech|thought|narration|sfx|sign|other`), `source_text`, `speaker`,
  `speaker_gender`/`addressee_gender` (`male|female|mixed|unknown`), `origin`
  (`local|model`), `warnings`, then derived `translation` (`None` or `{"text", "status":
  ok|overflow|missing|skipped, "note"}`) and `layout` (`None` or typeset output).
- Page: `page_id` (`p{index:03d}`), `index`, `source_name`, `image_sha256`, `width`,
  `height`, `regions`, `summary`, `status` (`pending|recognised|translated|rendered|failed`),
  `warnings`, `versions` (stage -> version string).
- Comic: `schema`, `comic_id`, `source_language`, `target_language`, `pages`, `notebook`
  (`characters`: `[{name, target_name, gender, note}]`, `terms`: `[{source, target}]`).

## Builder tasks (parallel; common base COMIC-0; separate files; conductor integrates in order A, B, C)

### COMIC-A — local detection. Owns `scholarly_translation/comic_detect.py`, `tests/test_comic_detect.py`.
`DETECT_VERSION = "comic-detect@1"`;
`detect_candidates(image) -> list[Candidate]` sorted top-to-bottom then left-to-right;
`snap_region(image, bbox) -> Candidate` (model box -> ink bbox tightened inside it and the
bounded light region containing it, `interior=None` when the fill leaks to the page edge or
exceeds a sane share of the page). Pure Pillow + stdlib (no numpy/OpenCV); work on a
downscaled copy (long edge about 1200 px) and map back. Accept: on `comic_fixtures` pages every
balloon and caption is found (IoU of text bbox >= 0.5), interiors contain the text bbox and
stay inside the drawn balloon, plain/complex background is classified correctly, no
candidate on empty art; a 2000x3000 page runs in < 5 s. Out: model calls, ordering by
reading direction, inpainting.

### COMIC-B — typesetting and rendering. Owns `scholarly_translation/comic_typeset.py`, `tests/test_comic_typeset.py`.
`TYPESET_VERSION = "comic-typeset@1"`; `font_for(target_code) -> Path` (bundled fonts:
Hebrew `culmus/HadasimCLM-Bold.ttf`, Latin `notosans/NotoSans-Regular.ttf`);
`min_font_px(page_height)`; `capacity(region, font_path, rtl) -> int` (approximate characters
that fit at a readable size; goes into the translation prompt);
`fit(region, text, font_path, rtl) -> Layout` with `{"style": bubble|box|subtitle,
"font_size", "line_height", "lines": [{"text" (logical), "x", "y", "width"}], "box",
"overflow": bool}`; `render_page(image, items) -> Image` (items = regions with `layout` and
translation; never mutates the input). Rules: `bubble` for text in a plain interior
(per-line width from the interior rows, centred, size between `min_font_px` and about 1.1x
the source `line_height`); `box` for text on art (`plain_background` false): a padded
rounded box in the sampled background colour covering the source text; `subtitle` for `sfx`:
original art kept, small text with a light stroke beside the source. Erasing fills the
dilated text ink box only inside the interior (or the bbox when there is none). RTL lines go
through `export_common.reorder_bidi_line`; greedy word wrap, a word is split only when it
cannot fit a line on its own. Accept: text stays inside the interior/box on fixture balloons,
largest size that fits is chosen, overflow is reported not hidden, Hebrew draws in visual
order, input image unchanged, deterministic output. Out: model calls, new fonts, inpainting.

### COMIC-C — model stages, pipeline, CLI. Owns `scholarly_translation/comic_model.py`, `scholarly_translation/comic_pipeline.py`, `scholarly_translation/runtime_prompts/14_comic_recognition.md`, `15_comic_translation.md`, `16_comic_shorten.md`, `tests/test_comic_model.py`, `tests/test_comic_pipeline.py`.
Model side: marked page image, prompts (templates localised with `target_languages.localize`
where the target matters), strict JSON validators (all ids answered, no extras, source not
translated in recognition, target script in translation, boxes in 0..1000 normalised space),
reconciliation, notebook merge (approved/earlier names win; conflicts become warnings).
Pipeline: input loading (image files sorted naturally, folder, CBZ/ZIP read without
extracting outside the job folder, PDF pages rendered with pypdfium2), page loop, calls
through `chapter_pipeline._controlled` with a `WorkJournal` and `ControlStore` in
`<out>/.state/` (a rerun replays validated answers and never resends), auto-retry of cheap
retryable failures under the `job_blocks` AUTO_ACCEPT rule, mock mode (no network,
conspicuous placeholder text, exercises layout), outputs (pages/NNN.png, comic.cbz, comic.pdf,
comic.json, review.html side by side), optional `--notebook` file shared across volumes.
CLI: `python -m scholarly_translation.comic_pipeline INPUT --out DIR --source-language
en|fr|ja --target he [--model mock|configured --model-config PATH] [--budget-usd 1.0]
[--pages 1-5] [--notebook PATH]`. Accept: offline tests with fake adapters for prompt
content, validators (good/bad answers), reconciliation, notebook, resume without resend,
output files, mock end-to-end on fixture pages; no live provider call.

## Invariants
Source image files are never modified; every model answer is validated before use; no paid
call in development; uncertainty is data (`warnings`, `overflow`, `origin`); unanswered
marks are dropped visibly (warning on the page), never silently.

## Out of scope (this round)
Web UI integration (next step after the engine is accepted), learned detectors or
inpainting models, new font downloads, vertical target text, editing UI for regions,
translation quality claims (needs real pages and human judgement).

## Acceptance (conductor)
Each builder's tests pass in its worktree; after sequential integration the full offline
suite passes; a mock end-to-end run on fixture pages produces all outputs with every
translated line inside its region (checked geometrically, plus a visual look at one page).
Real-comic quality stays BLOCKED until the user supplies pages and approves a paid run.
