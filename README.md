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

## Gate 6: bounded provider adapter and live access probe

`model_adapter.py` defines a provider-independent diagnostic request/result boundary
(schema 1), separate from the translation provider config in Gate 1's `provider.py` and
unrelated to translation memory. A mock adapter is deterministic and non-billed; an
optional OpenAI adapter (exact model `gpt-6-luna`, Responses API, official SDK) is
imported and used only inside `probe-provider --provider openai`. This is provider
plumbing only, not a translation job, not model-quality evidence, and never
auto-approved.

```
python -B -m scholarly_translation probe-provider --provider mock --output outputs/gate6-mock
python -B -m scholarly_translation probe-provider --provider openai --output outputs/gate6-live
```

Both probes send a fixed, small synthetic English phrase through the same validated
request schema (`profile_id=scholarly`, synthetic marker, `target_language=he`, source
SHA-256, prompt/config version). The mock probe runs offline with no credential or SDK.
The OpenAI probe requires the official `openai` Python package installed locally
(`pip install openai`; not bundled in `requirements.txt`, since it is optional and only
this one probe path imports it) and an `OPENAI_API_KEY` in the process environment; the key is never stored, logged, or printed,
and the probe refuses to run with an explicit local-setup error before any network attempt
if either is missing — there is no silent fallback to mock. The call uses `store=False`,
no tools, `reasoning.effort=none`, a 256-token output cap, a single attempt
(`max_retries=0`) and a 20-second timeout. Standard list rates (verified 2026-09-30) are
$0.10/M input, $0.01/M cached input, $0.125/M cache write, $0.50/M output tokens; the
fixed diagnostic phrase with the 256-token cap is estimated below $0.01 per call. Reported
usage produces a list-price estimate; missing or invalid usage is recorded as
`not_metered` rather than an invented charge, and the actual account charge is always
recorded as `unknown`. An incomplete or empty model response is an explicit failure, never
an approved result. Output is written to `probe_result.json` under `--output`; the CLI
refuses to overwrite an existing result file or write into the source/test tree, and
printed/persisted output is summary metadata only (status, duration, token usage,
estimate) with no credential or private source text.

## Gate 8: conditional semantic review and one bounded correction

`semantic_review.py` binds a Gate-7 `translation-draft@1` record to its canonical
source/policy identity and, only when deterministic risk flags fire (negation,
quantifier/scope-modality words, Japanese context-dependence, selected OCR
warnings, an unapproved loaded term, or a Gate-7 formal finding), runs a
replaceable, bounded critic over the target unit, same-reading context, approved
terms and the Hebrew draft -- never a whole PDF, translator rationale or model
name. Critic claims are only accepted when their source/target spans are grounded
in the real source/draft text; malformed or ungrounded claims go to a human. At
most one validated, correctable claim may trigger one bounded correction, which is
rechecked with the Gate-7 formal checker and the same deterministic grounding
before being offered as an unapproved candidate. OCR/source uncertainty and
formal/terminology findings always bypass the critic straight to a human; no
model ever repairs the source. Output is always `approved: false`.

```
python -B -m scholarly_translation semantic-review STRUCTURE_JSON --glossary GLOSSARY_JSON --draft TRANSLATION_DRAFT_JSON --provider mock --output outputs/gate8-mock
```

The result records `scholarly-semantic-review@1` and a review cache key derived
from the exact draft, profile, resolved risk triggers, review policy, provider and
models. The key is provenance only; no persistent review cache is used.

Status is one of `not_triggered`, `needs_human`, `corrected_unapproved`,
`needs_human_or_budget`, or an explicit failure status; synthetic fixtures and
the fake critic/corrector establish software behavior only, never reviewer
accuracy or scholarly quality.

## Gate 7: first source-bound translation draft and formal checks

`translation.py` resolves the smallest scholarly-profile translation job from an existing
validated Gate-4 structure unit and a fresh Gate-5 glossary resolution, through the
Gate-6 generic text-generation adapter added to `model_adapter.py`, to an unapproved
Hebrew draft plus deterministic formal findings from `formal_checks.py`. This gate does
not select a quality winner between providers and never auto-approves a draft.

```
python -B -m scholarly_translation translate-unit STRUCTURE_JSON --glossary GLOSSARY_JSON --unit-id UNIT_ID --profile scholarly --provider mock --output outputs/gate7-mock
```

`profile_id` must be exactly `scholarly` (no profile registry, no fallback); source
language must be `en`, `fr` or `ja`, target language is fixed at `he`. The request is
refused before any network call for an unresolved reading, continuity findings, a
missing/stale unit, a conflicting glossary resolution, malformed source/policy input, or
an oversized prompt. Context sent to the provider is bounded to the target unit plus at
most one previous/next unit from the *same* reading, each with an explicit role
(`previous`/`target`/`next`); it never crosses page/document/readings and never sends a
whole PDF. Only applicable approved glossary rule source/target/version/loaded fields
enter the provider prompt and effective policy fingerprint; proposed loaded terms create
human-review findings and are never sent as instructions. A deterministic cache key is computed from profile, exact source/reading/
unit spans and hashes, neighbor hashes, the effective glossary policy fingerprint,
provider/model and prompt/config/decoding parameters, but this gate keeps no persistent
cache and performs no automatic translation-memory approval.

For OpenAI, use `--provider openai` and a new output directory. The local
gateway bounds the prompt, reserves a conservative token-price estimate before
the call, allows one call per CLI invocation with no retry, and records usage and
50%/80% budget notices. A caller translating several units must reuse one
`TranslationBudget` object to enforce a cumulative list-price cap; actual
account charges cannot be enforced from the API response.

The mock adapter produces a conspicuous `[GATE7-MOCK-PLACEHOLDER-NON-HEBREW]` placeholder
and is never counted as a real translation. The optional OpenAI path reuses the Gate-6
`gpt-6-luna` boundary (`store=False`, no tools, `reasoning.effort=none`, 256-token output
cap, `max_retries=0`, 20s timeout); a missing key/SDK fails before any network attempt,
and a transport/incomplete/empty response is an explicit, sanitized failure. `formal_checks.py`
is a separate, pure checker that reports typed findings (missing numbers, footnote
markers, citation/reference tokens, formula-like expressions, proper-name candidates,
missing Hebrew script) using Unicode-normalized exact token counts; it never rewrites
text, asserts a transliteration is wrong, or sets approval. A formally clean draft remains
`draft_unapproved`; any finding yields `needs_human`. Output is one
`translation_draft.json` under `--output`, including failures with any observed usage; the
CLI refuses to overwrite an existing draft, to write into the source/test tree, or to
collide its output with the structure/glossary/source evidence, and prints summary
metadata only. The draft is schema-1 `translation-draft@1`: it is not approved memory, a
final translation, or a review/export artifact.
