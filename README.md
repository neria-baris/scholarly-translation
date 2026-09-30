# Gate 1 offline skeleton

Standard library only, Python 3.9+. No network calls, no dependency installation.

Current records use schema 2: document/page/region/segment IDs, source URI/language,
processing stage/version, input-file SHA-256, status and warnings. Schema 1 remains
readable with an explicit legacy warning when an input hash was never recorded.
The demo is synthetic software evidence; it establishes no PDF/OCR or translation quality.

## Run the demo

```
python -B -m scholarly_translation demo --output outputs/gate1
```

Writes `outputs/gate1/source.txt` (synthetic multilingual text), `outputs/gate1/document.json`
(persisted document/page/segment records), and appends a mock-provider usage event to
`outputs/gate1/usage.jsonl`. Rerunning demo reuses the same deterministic IDs and appends
another usage record.

## Inspect a document

```
python -B -m scholarly_translation inspect outputs/gate1/document.json
```

Prints schema/document version, source locator, and page/segment IDs, offsets and text.
Exits nonzero if the file is missing or invalid.

## Run tests

```
python -B -m unittest discover -s tests -v
```

## Provider configuration

See `config.example.json`. Only the `mock` provider (model `mock-echo-1`) is supported in
this gate; any other provider or model name is rejected before any call. Mock output is
always prefixed with `[MOCK-PLACEHOLDER]` and is never a real translation. No secrets are
used or logged.

Pass `--config path/to/config.json` to `demo` to override the target language (or explicitly
select mock/`mock-echo-1`):

```
python -B -m scholarly_translation demo --output outputs/gate1 --config config.example.json
```

The config is loaded and strictly validated (object shape, known fields only, correct field
types) before anything is written or any provider is invoked. Unknown fields (including
credential-like ones) are rejected by name only — their values are never printed or logged.
Omitting `--config` uses the built-in mock defaults.

## Gate 2: digital PDF extraction

Requires `pdfplumber` and `reportlab` (see `requirements.txt`; `reportlab` is only used to
generate tiny original test fixtures). Records now use schema 3: Segment gains an optional
`bbox` ([x0, top, x1, bottom] in PDF points) and Page gains optional `width`, `height` and
`source_text`. Schema 1 and 2 documents remain readable.

```
python -B -m scholarly_translation extract-pdf INPUT.pdf --language en --output outputs/gate2
```

Writes `outputs/gate2/document.json` (extracted document/page/segment records with bbox and
page-local source_text), `outputs/gate2/page-N.png` (page renders at 110 DPI), and
`outputs/gate2/comparison.html` (escaped static HTML comparing renders to extracted text).
Extraction uses only basic top-to-bottom, then left-to-right reading order; output status is
always `needs_human` with a `layout_unverified` warning — extraction is not semantic
acceptance. Empty pages are retained and flagged `page_N_empty_needs_ocr`. Invalid, empty,
encrypted or missing PDF input raises a bounded `ExtractionError` with no page content. No PDFs
are committed to this repository; tests generate tiny original fixtures in temporary
directories.

## Gate 3: local OCR fallback

OCR runs a single local Tesseract engine on image-only or failed-text pages of a validated
schema-3 Document, using the exact original PDF whose bytes match `input_hash`. It writes a
separate OCR bundle (schema 1) alongside rendered page images at 200 DPI; it never overwrites
`document.json` or `source_text`. Bundle pages are always `status: needs_human`,
`eligible_for_translation: false`, carry an `ocr_unreviewed` warning (plus `low_confidence`,
`empty`, or `error` as applicable), and OCR confidence is never proof of accuracy.

```
python -B -m scholarly_translation ocr-pdf INPUT.pdf outputs/gate2/document.json \
    --language en --output outputs/gate3 \
    --tesseract "C:/Program Files/Tesseract-OCR/tesseract.exe" \
    --tessdata-dir cache/ocr/tessdata
```

By default only pages with empty extracted text are OCR'd; pages with digital text are skipped
and listed with reason `digital_text_available`. Pass `--pages 1 2` to force specific pages
(flagged `forced_page_review`); an invalid or mismatched selection raises a bounded
`OCRInputError` before any engine call. Supported `--language` values are `en`/`fr`/`ja`,
mapped to Tesseract's `eng`/`fra`/`jpn`. Engine failure, timeout, a nonzero exit, or malformed
TSV output leaves the affected page `needs_human` with an error code and empty text. Successfully
rendered images are retained; rendering failures keep the original PDF/page reference and an error.
The engine subprocess runs with a finite timeout (maximum 120 seconds) and list
arguments (no shell), and engine stderr/private paths are never included in bundle or log
output. Requires a local Tesseract OCR install (5.4.0 tested) and optionally a local, uncommitted
`cache/ocr/tessdata` directory for language weights; no network calls are made.
Standalone language directories need no `configs/tsv` file: TSV output is selected explicitly.
The clear/degraded English, French and Japanese fixtures demonstrate plumbing and review flags,
not real scholarly OCR accuracy. Japanese word spacing is preserved as returned by the engine.

## Gate 4: source reading and segmentation

Chooses an inspectable reading per page from validated digital and/or OCR evidence and turns a
resolved reading into versioned, source-linked translation units. A reading is never
auto-approved: without an explicit human decision it stays `unresolved` (`unreviewed_source` or
`missing_source`) and produces zero units. A decision must name an exact candidate hash the
reader emitted for that page; a model actor, a stale hash or an unknown page is rejected.

```
python -B -m scholarly_translation structure DOCUMENT_JSON --output outputs/gate4/structure.json \
    [--ocr OCR_JSON] [--decisions DECISIONS_JSON] [--boundaries BOUNDARIES_JSON] \
    [--previous PREVIOUS_JSON]
python -B -m scholarly_translation inspect-structure outputs/gate4/structure.json
```

`--decisions` is a JSON object mapping `page_id` to
`{"origin": "digital"|"ocr", "candidate_hash": ..., "actor": ..., "actor_kind": "human", "reason": ...}`.
Default units are source lines; `--boundaries` maps `page_id` to a list of `[start, end]` half-open
spans to merge or split lines without ever silently joining or normalizing source text. Passing
`--previous` (an earlier `structure.json`) preserves stable reading/unit IDs for unchanged content,
creates a new reading version with a prior-version reference when the selected source changes, and
keeps a flat history of prior reading/unit snapshots. `inspect-structure` re-validates a persisted
structure file (rejecting malformed or tampered data) and prints reading/unit status and a
deterministic continuity report (gaps, overlaps, duplicate coverage, mismatched text, invalid
anchors). Fixture evidence demonstrates plumbing only; it is not scholarly source approval.

The source reader and segmentation are pure standard-library components. Evidence fingerprints
bind decisions to the complete digital/OCR candidate, not just matching text. OCR engine/model,
image geometry, confidence, warnings and failed alternatives remain inspectable. Replaying the
same inputs with the prior result returns it unchanged; changed boundaries preserve complete
snapshots and increment affected unit versions. A boundary plan with missing source characters
is rejected. JSON consumers reject duplicate keys, and the CLI refuses to overwrite evidence inputs.

Validation checks declared hashes, geometry and internal provenance; it does not reopen image/PDF
bytes or authenticate the asserted human actor. A simulated human decision in a fixture is only
a construction test. Default source lines do not establish scholarly paragraph or footnote
association; uncertain readings remain unresolved until a real human chooses the evidence.

## Gate 5: versioned terminology glossary and approved translation memory

A pure, versioned scholarly-terminology glossary (`glossary.py`) plus an exact source-bound,
human-approved translation memory (`translation_memory.py`). Glossary proposals are supplied
locally, never generated by a model in this product; every approval, rejection or revision
requires an explicit human assertion (`actor_kind: "human"`), including for terms marked
`loaded`. A model actor or a stale expected rule version/fingerprint is rejected. Proposed rules
are evidence only — they never become effective policy until approved. Source bindings (document,
page, reading version/hash, unit version/hash, exact absolute term span) are immutable once
proposed; history is a flat, append-only list of rule versions, never rewritten or deleted.

```
python -B -m scholarly_translation terminology STRUCTURE_JSON --glossary GLOSSARY_JSON \
    [--memory MEMORY_JSON] [--action ACTION_JSON] --output OUTPUT_DIR
```

`--glossary`/`--memory` may point at a file that does not yet exist; it is treated as a fresh,
empty store (no existing glossary is required for a first proposal). `--action` is an optional
JSON object tagged by `"action"`:

- `propose`: `{"action": "propose", "unit_id", "source_language", "source_char_start",
  "source_char_end", "target_term", "scope": {"document_ids": [], "unit_ids": []}, "loaded": bool}`
  — spans are absolute offsets into the unit's resolved source reading text.
- `review`: `{"action": "review", "rule_id", "expected_version", "expected_rule_fingerprint",
  "actor", "actor_kind": "human", "reason", "status": "approved"|"rejected",
  "target_term"?, "scope"?}` — `expected_rule_fingerprint` is the deterministic fingerprint of
  the current rule row (as printed in `glossary.json`); a stale version or fingerprint is refused.
- `resolve`: `{"action": "resolve", "unit_id"}` — writes `resolution.json` with the applicable
  approved rules, separately listed proposed rules, a `ready`/`needs_human` status (conflicting
  approved targets for the same term are never silently chosen), warnings and a deterministic
  effective-policy fingerprint scoped to only the rules that actually apply.
- `remember`: `{"action": "remember", "unit_id", "target_text", "actor", "actor_kind": "human",
  "reason"}` — records a manually supplied, human-approved Hebrew target text keyed to the exact
  unit/source binding and the current applicable-approved-policy fingerprint; refused unless
  terminology resolution for that unit is `ready`.

Output is always written as separate `glossary.json` (and `memory.json`/`resolution.json` when
relevant) under `--output`, never overwriting the structure or action input files. Strict,
duplicate-key-rejecting JSON is used throughout; invalid input exits nonzero with no traceback
and writes nothing. A translation-memory lookup (`translation_memory.lookup`) returns
`miss`/`reusable`/`stale_dependencies`/`needs_human` with reasons: only an exact unit/source match
under an unchanged, `ready` applicable-approved policy is reusable, and a later revision of an
approved rule invalidates only the lookups that actually depend on it. There is no fuzzy search,
embeddings or real translation cache in this gate, and glossary/memory entries are fixture-level
plumbing, not an assertion of real scholarly terminology quality.
