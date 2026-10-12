# COMIC-SIGNS-ERASE — balloon-wide erase, separated neighbours, signs re-lettered by an image model

Date: 2026-10-12. User feedback with examples: neighbouring balloons overwrite each other; signs and
names drawn on objects should be edited in the picture by an image model rather than covered by a
pasted box; erasing the original lettering must not depend on the translation and must leave no
residue.

Owns: `comics/detect.py` (snap returns the free light area as `balloon`), `comics/records.py`
(`balloon`/`room` carried and mirrored), `comics/typeset.py` (`_erase_balloon`; erase pass over every
balloon region before any text, regardless of translation; edited signs drawn by nobody else),
`comics/pipeline.py` (`separate_regions` against neighbours' lettering and text rows, `make_room`,
overflow refit into `room`, sign editing in `_render`, CLI flags), `comics/edit.py` (new).

Erase: every dark component lying wholly inside a balloon's free light area (not touching its edge)
is painted with the background; outlines, tails and art reach outside and stay.
Sign edit (`--edit-signs on`, default off; `--edit-budget-usd` 1.0; `--edit-quality` medium): one
`gpt-image-2` masked edit per sign on a crop of the output page (after mirroring, so Hebrew reads
correctly); only the masked lettering area is pasted back (feathered); results cached by request
hash in `<out>/.state/edits/` and never requested twice; usage and a list-price estimate in
`edits.jsonl` (rates as the cover feature, labelled estimate); ceiling stops further edits; a failed
or refused edit keeps the backing patch with warning `sign_edit_failed`. Separate from the text
budget store (as the cover feature).

Acceptance: offline tests (erase without translation, request/mask, paste only inside the mask,
cache, ceiling, failure). Live check on two signs is evidence only.

Update 2026-10-12 (user): not only signs — every piece of lettering in the artwork. `is_art_text`:
kind sfx or sign, or any region set as a backing box or subtitle (text on art). Flag renamed
`--edit-art-text` (old `--edit-signs` kept as an alias). First path: minimal local regeneration of a
tight crop (no mask), pasted whole with a faded edge, accepted when the crop's outer band changes
<= 18; fallbacks: masked redraw, then locate/clean/letter; a failure keeps the box or subtitle.
