# Scholarly translation

## Simple local document UI

Run `./run-ui.ps1` on Windows (or `Run Scholarly Translation.vbs` at the repo
root) to open the local, single-user web UI: upload a PDF with embedded text
or an EPUB, choose Academic/Literary, a catalogue model or Other, independent
QA model, a quality mode (Fast/Checked/Thorough) and a per-document budget.
Supply the selected providers' API keys in the protected local session, inspect
the full translation/QA/correction cost preview, then translate and download the
translated document in the **same format you uploaded** (PDF stays PDF,
EPUB stays EPUB). Per-unit review/editing is optional and never a condition
for downloading a result. "Auto" with no model configured is an explicit,
free, non-network UI demo (mock placeholder text), not a translation. Select
one of five bundled Hebrew PDF fonts before translation or change the download
font afterwards: rerendering saved text makes no model call. See
[the Hebrew UI guide](UI_README_HE.md) for setup, limits and storage, and
[INSTALL_HE.md](INSTALL_HE.md) for first-time setup with no command line.
If PowerShell blocks scripts, use the VBS launcher or
`powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run-ui.ps1`;
this applies only to that process, without changing machine policy.

This user-directed document flow (`scholarly_translation/document_draft.py`,
`document-draft@2` records) drives the same canonical pipeline as the CLI
gates below: `document_structure.py` (schema 2: nodes/units/
unit_node_links) → `context_strategy.py`'s chapter-aware, model-budget-based
context selection, extended with `document_state.py`'s small, versioned,
source-backed cross-chapter memory (approved terminology/definitions/
character register/unresolved ambiguities carried from one chapter into the
next, never a chapter summary) → `chapter_pipeline.py`'s model-fit whole-chapter
or semantic-unit batches → quality-mode-gated `review_qa.py` (risk-based/all-unit
semantic review, chapter QA, one bounded correction and focused recheck) → `export_pdf.py`
/ `export_epub.py`. Chapter-level QA can propose persistent-state updates;
a proposal that contradicts existing state is surfaced, never silently
applied (see "Translation context, chapter QA and persistent state" below).

Every live translation, review and chapter-QA call for one document shares
a single persistent per-document budget and cache
(`runtime_controls.ControlStore`/`PersistentBudget`/`RuntimeCache`, Gate 11):
review/QA calls are no longer a separate, unmetered path, and the job's
displayed cost estimate reflects every stage, not translation alone. Source
remains unreviewed and all drafts remain unapproved, including human edits;
this does not bypass scholarly approval or establish Gate-10 quality.
Model limits and Standard prices are dated 2026-10-05 in `model_catalog.py`;
OpenAI and Anthropic usage is normalized, including observed cache reads/writes.
Other models use explicit manual rates or a labelled price assumption, never an
official arbitrary-provider quote. Local `tiktoken`/byte sizing reports its method
and uncertainty; the current GPT-6/Claude mappings remain estimates. See
[token and cost notes](MODEL_COSTS_HE.md).

`work_journal.py` persists each step's raw response before parsing/accounting;
received/completed work resumes without another request. An uncertain dispatch
blocks automatic resend. Pause stops before the next request after retaining the
current response. Memory-only keys must be supplied again after server restart.
Stage/chapter progress and observed estimated spend, held funds, remaining budget,
local reuse and provider cache tokens are separate. Software acceptance does not
establish scholarly quality; the representative human pilot remains pending.

## Gate 1 offline skeleton

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

## Gate 9: local human review, decision and bilingual export

`human_review.py` binds a Gate-4 structure, Gate-5 glossary, Gate-7
`translation-draft@1` and an optional Gate-8 `semantic-review@1` to one
reviewable unit, renders a static offline review page (source text with its
PDF page or OCR image preview and exact page/unit/span, Hebrew draft, formal/semantic flags,
applicable glossary, and any Gate-8 correction), and validates a *separate*
explicit human decision JSON -- actor, reason, a candidate text bound to its
declared origin (`draft`, Gate-8 `correction`, or a `human_edit`), and an
explicit `approve`/`defer` action. The page has a local form to edit/select
the candidate and download a decision JSON. Its action starts blank and the
download alone grants nothing; submit the file through the CLI.

```
python -B -m scholarly_translation human-review-render STRUCTURE_JSON --glossary GLOSSARY_JSON --draft TRANSLATION_DRAFT_JSON [--review SEMANTIC_REVIEW_JSON] --output outputs/gate9-render
python -B -m scholarly_translation human-review-decide STRUCTURE_JSON --glossary GLOSSARY_JSON --draft TRANSLATION_DRAFT_JSON [--review SEMANTIC_REVIEW_JSON] --decision DECISION_JSON [--previous PRIOR_RECORD_JSON] --output outputs/gate9-decide
python -B -m scholarly_translation human-review-export STRUCTURE_JSON --glossary GLOSSARY_JSON --draft TRANSLATION_DRAFT_JSON [--review SEMANTIC_REVIEW_JSON] --record HUMAN_REVIEW_JSON --output outputs/gate9-export
```

A unit flagged by any Gate-8 critic-eligible or bypass-to-human risk trigger
(negation/quantifier/scope-modality, Japanese context-dependence, OCR source
uncertainty, an unapproved loaded term) requires a bound Gate-8 review before
approval; a unit flagged only by a plain formal finding does not, since Gate 9
reruns the Gate-7 formal checker itself. Missing numbers, notes, references,
formulas or Hebrew script must be corrected before approval; other formal
findings need an explicit `formal_override_reason`. No supplied `actor_kind`
or other field outside the fixed decision schema can grant approval -- the
record always sets `actor_kind: "human"` itself and strict field checking
refuses anything else. A revision supplies the prior record and its exact
`prior_decision_hash`; records are never overwritten, and `human-review-decide`
refuses to overwrite an existing decision file or create an unlinked second
record in the same history directory. `human-review-export` checks the latest
decision in that directory and renders
escaped bilingual HTML (explicit `dir="ltr"` source, `dir="rtl"` Hebrew, with a
link back to the exact PDF page or OCR image) only for a record whose
`status` is `approved`, whose hashes still match the exact structure/draft/
review being exported, and whose stored formal findings still match a fresh
recheck -- a deferred, stale, tampered or merely-unapproved record is refused.
Synthetic actor/approve decisions in tests are explicitly test-only and prove
software behavior, not real human judgment.

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

## Session C: optional semantic review, candidate comparison and chapter QA

`review_qa.py` is a lightweight, provider-neutral review/evaluation layer over
already selected source/context and already produced Hebrew. It is independent
of `segmentation.py`, context selection, Gate-8 correction behavior, provider
adapters and persistent budget/cache/schema state, and establishes no
translation quality, model selection or human approval by itself. It faithfully
renders three versioned runtime prompt assets under `runtime_prompts/`
(`04_independent_semantic_review.md`, `05_candidate_comparison.md`,
`06_chapter_level_qa.md`) and calls a minimal injected
`generate(prompt_text, model)` callable (the same shape as
`model_adapter.TextGenerationAdapter.generate`); it never calls a paid
provider itself, makes no network/Git access, and writes no user content; it
only reads the three bundled prompt assets. The supplied assets remain
byte-identical; candidate and chapter prompts receive a short
appended structured-output contract so their free-form `...` sections can be
validated deterministically and fail closed.

**Unit review** (`build_unit_review_request` / `run_unit_review`) takes a
source unit text, a Hebrew translation, optional source context and glossary
decisions, and a `policy` of exactly `off`, `risk_based` or `all`, plus
caller-supplied `risk_flags` (`translation_notes`, `extraction_or_ocr_risk`,
`formal_check_failure`, and a free-form `configured_risk_flags` list). `off`
always skips; `risk_based` skips unless at least one risk flag is set; `all`
always calls the adapter. These flags are routing evidence only, never a
semantic verdict. The result is `VERDICT: PASS` with no issues, or `REVISE`
with one or more `CRITICAL|MAJOR|MINOR` issues, each carrying a source span
and a translation span that must be a literal grounded substring of the
supplied source/translation text respectively. A `PASS` with issues, a
`REVISE` with none, an unparseable response, or an ungrounded span is rejected
and the record's status becomes `needs_human` rather than fabricating a
verdict.

**Candidate comparison** (`build_candidate_comparison_request` /
`run_candidate_comparison`) takes a source unit text and exactly 2 or 3
anonymously identified candidate translations (`{"A": "...", "B": "..."}`),
always calling the adapter. The result preserves material differences (each
tagged `stylistic_only`, `genuine_interpretive_difference` or
`likely_translation_error`), a per-candidate assessment for every known
candidate id, and a `best_supported_translation` that must be one of the
known candidate ids or `NO_CLEAR_WINNER`. An unknown winner id, a missing
per-candidate assessment, or an unparseable response routes the record to
`needs_human`.

**Chapter-level QA** (`build_chapter_qa_request` / `run_chapter_qa`) takes a
fully assembled source chapter and Hebrew chapter, an optional profile and
glossary decisions, and a `policy` of exactly `off` or `on`. `off` always
skips without calling the adapter. `on` returns `VERDICT: PASS` or `REVISE`
with one or more issues, each categorized as `completeness`, `consistency`,
`continuity` or `hebrew_quality`, carrying a severity and a span that must be
a literal grounded substring of either the source or Hebrew chapter, and a
local correction -- never a wholesale retranslation.

All three record types are schema-versioned (`unit-review@1`,
`candidate-comparison@1`, `chapter-qa@1`), always carry `approved: false`,
and record hashed input identity, the byte hash/version of the prompt asset,
provider/model identity and a bounded provenance `call`
entry (prompt hash, observed model, token usage, estimated cost at the
Gate-6/7 pricing table, and provider status) whenever the adapter is actually
invoked; skipped paths carry `call: None` and never invoke the adapter.

```python
from scholarly_translation.review_qa import build_unit_review_request, run_unit_review

request = build_unit_review_request(
    source_text, hebrew_translation, policy="risk_based",
    risk_flags={"formal_check_failure": True},
)
review = run_unit_review(request, generate=my_generate_callable)
```

Limitations: this module treats all inputs as data, never instructions; it
performs no automatic source repair, translation generation/correction, or
mandatory review, and makes no real scholarly-quality or human-approval
claim. Deterministic fakes in `tests/test_review_qa.py` establish parsing and
routing behavior only, never reviewer accuracy.

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

## Gate 11: persistent budget, cache and usage controls

`runtime_controls.py` is a small, SQLite-backed call boundary shared by
`translate-unit` and `semantic-review`: it durably reserves a conservative
list-price amount and call slot before any live provider request, records
observed usage (never prompt/source/output text), and lets a bounded cache
reuse a prior successful raw adapter result instead of dispatching again.
It never grants approval. Every public translation/review invocation uses
persistent controls, including mock dispatches. Direct Python callers without
controls retain the legacy process-local `TranslationBudget`.

```
python -B -m scholarly_translation translate-unit STRUCTURE_JSON --glossary GLOSSARY_JSON --unit-id UNIT_ID \
    --profile scholarly --provider openai --output outputs/gate11 \
    --control-store outputs/runtime_controls.sqlite3 --task-id my-document --max-calls 3 --hard-list-usd 0.01
python -B -m scholarly_translation semantic-review STRUCTURE_JSON --glossary GLOSSARY_JSON --draft DRAFT_JSON \
    --provider openai --output outputs/gate11-review --control-store outputs/runtime_controls.sqlite3 --task-id my-document
python -B -m scholarly_translation runtime-status --control-store outputs/runtime_controls.sqlite3 --task-id my-document
```

`--control-store`, `--task-id`, `--max-calls` (default 3) and `--hard-list-usd`
(default 0.01) are optional on `translate-unit`/`semantic-review`; omitting
`--control-store` uses `outputs/runtime_controls.sqlite3`.
The database at `--control-store` is created if missing
(parent directories too) and reused across invocations; a task's policy
(`max_calls`, `hard_list_usd`, pricing version, output cap) is fixed the
first time the task is created and a later mismatched policy is refused
rather than silently reset. `--task-id` defaults to the unit's
`document_id`, so translation and review share one budget per document.
`runtime-status --control-store PATH --task-id ID` is read-only and never
creates a missing store; it reports the task's cap, attempted/settled call
counts, held and list-estimated amounts, a stopped flag, cache-hit/miss counts
and a privacy-safe per-event log (stage, outcome, reserved/observed
amounts, actual-charge placeholder, timestamp) with no prompt, source or
output text. Usage events are append-only and cache hits link to their original
completed event. A control-store path may not be inside the package/tests,
Git, configuration or audit trees, occupy a repository root file, or alias
protected source evidence (including SQLite sidecars). Missing, empty, unrecognized-schema or
tampered cache/task rows fail closed (an explicit error) rather than being
auto-repaired or reset. A cache hit (same exact source/policy/provider/
config identity and stage) skips the provider dispatch and its cost
entirely; translation/semantic-review formal and grounding checks are
always rerun against the cache-derived text regardless of its origin. The exact
prompt, stage, actual requested model and gateway output cap are also bound.
Current cache-hit usage/cost is zero; historical token usage is separate provenance.
Atomic claims prevent duplicate in-flight dispatches across processes. Unknown or
failed potentially started calls retain their reservation and freeze the task;
usage above a reservation also freezes it. There are no automatic retries.

This gate reuses Gate 6/7's rate constants and output-token cap for its
offline worst-case reservation math; these remain dated list-price
estimates, not a verified account-billing cap, and the actual charge is
recorded as `unknown` for live calls, `no_provider_call` for cache reuse, and
`synthetic_non_billed` for mock events. Reverify pricing before a new live request.
Acceptance uses fake/mock adapters and makes no paid runtime provider call.

## Gate 10: offline evidence-based quality pilot evaluation

`evaluation.py` validates a human-labeled schema-1 `pilot-manifest@1` (exact source/reading/
unit binding, explicit human-approved source and Hebrew reference hashes, one or more
comparable candidate arms per unit with provider/model/prompt/context-policy/critic-enabled
identity, a shared glossary hash, a draft hash and human review attestation,
observed/list-estimated cost/latency/correction minutes, and MQM-style expert
span/error annotations with severity, actor and reviewer verdict) and computes a
deterministic schema-1 `pilot-report@1`. This gate makes no provider call, infers no
semantic truth from model output, and never selects a model winner or routing
recommendation — that remains a separate, later, human-made deliverable requiring a
genuinely balanced gold set under full Gate-10 acceptance.

```
python -B -m scholarly_translation evaluate-pilot MANIFEST_JSON --output outputs/gate10
```

Strict validation requires: an explicit `actor_kind: "human"` actor and reason, with a
matching SHA-256 hash, for both the source text and the approved Hebrew reference per unit;
exact source span/text-length binding and a positive, expert-recorded `source_word_count`
(especially important for Japanese, where whitespace splitting is not a word count);
a consistent `pdf_hash` per `document_id`; a consistent provider/model/prompt/context-policy/
critic-enabled/glossary signature for every reuse of the same `arm_id`; matching draft hashes
for human review attestations; shared glossary hash and page denominator across a unit's arms;
unique unit, arm and annotation IDs; supported `en`/`fr`/`ja` source
languages; and finite, non-negative numeric fields throughout. Annotations require
`expert_reviewed: true` on their arm. Malformed, duplicate or nonfinite JSON, an unsupported
language/category, or any of the above invariant violations is refused before any report is
computed or written.

The report gives sample counts by language/genre/OCR level and experimental arm; per-arm,
per-language and per-language/genre critical errors per 1,000 source words (counted once per
unique confirmed source span/type; false-positive reviewer flags are excluded), severity
counts, correction minutes/page, list-estimated cost/page, p50/p95 latency, and reviewer
true/false-positive counts where verdicts are present; measured context-policy and critic
deltas and their missingness per unit; and explicit
missing-data/uncertainty notes. Each source segment counts once across its arms and must have
expert review for every arm. A report built from fewer than 72 such segments
(24 per `en`/`fr`/`ja`) or missing a paired context or critic arm for any unit is `preliminary`;
`model_winner` and `recommendation` are always `null`. Output is one exclusive
`pilot_report.json` under `--output`; the CLI refuses to overwrite an existing report or write
into the source/test tree, and prints only counts/status to stdout. Synthetic fixtures in
tests demonstrate arithmetic/software construction only, never real expert judgment.

## Role-based provider and model selection

The scholarly runtime is no longer tied to one live provider or a fixed model
allowlist. `model_config.example.json` is the versioned, secret-free schema for
the `translator`, `semantic_reviewer`, `chapter_qa`, `candidate_evaluator`, and
optional `context_state_builder` roles. Each role selects a provider and an
arbitrary nonempty model ID and supplies its own context window, usable context
budget, optional output limit, and structured-output capability. The same
provider/model may be assigned to every role. Capability values are deployment
metadata and should be checked against the provider before a live run.

Built-in adapter types are `openai`, `anthropic`, and `deepseek`; a named
`openai_compatible` provider requires an explicit HTTPS `base_url`. Credential
values never belong in JSON. Configuration contains only the environment
variable name: `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `DEEPSEEK_API_KEY`, or the
uppercase name chosen for a compatible endpoint.

SDKs are optional and imported only at dispatch time. OpenAI and compatible
providers use the `openai` Python package; Anthropic uses `anthropic`. Missing
credentials or SDKs fail before a request. Provider failures are sanitized,
and no adapter silently switches provider or model.

The committed price table is still the dated OpenAI table used by the existing
budget gateway. Other provider types record token usage when returned but mark
price as `not_metered`, retain the conservative reservation, stop further calls,
and do not cache that response. Add verified provider-specific pricing before
enabling multi-call automated runs for those providers.

Use the role configuration on the existing CLI boundaries:

```
python -B -m scholarly_translation translate-unit STRUCTURE_JSON \
  --glossary GLOSSARY_JSON --unit-id UNIT_ID --profile scholarly \
  --model-config model_config.example.json --output OUTPUT_DIR

python -B -m scholarly_translation semantic-review STRUCTURE_JSON \
  --glossary GLOSSARY_JSON --draft DRAFT_JSON \
  --model-config model_config.example.json --output OUTPUT_DIR
```

The commands resolve `translator` and `semantic_reviewer`, respectively.
Provider/model/capability identity participates in cache identity. Requested
and observed provider/model identity is recorded in draft/review provenance.
Session C's optional unit review, candidate comparison and chapter QA expose
matching `build_*_request_for_role()` helpers for `semantic_reviewer`,
`candidate_evaluator` and `chapter_qa`; their records carry the resolved
provider/model/capabilities. `context_state_builder` remains validated and
available through `ModelConfiguration.resolve()` because no context-building
workflow exists yet.

Legacy `--provider mock|openai` commands and Gate-1's `config.example.json`
remain readable. The simple document UI's "Auto" model choice is a separate,
free, OpenAI-only-when-configured convenience path with its dated model/price
table and never silently consumes role configuration; choosing "configured"
in that UI instead resolves `translator`/`semantic_reviewer`/`chapter_qa`
exactly through this same `ModelConfiguration` (Session G: see "Simple local
document UI" above). Multi-provider credentials and base URLs stay in
environment/configuration rather than the upload screen.

## Translation context, chapter QA and persistent state (Sessions D/G)

`context_strategy.py` chooses, per translation unit, between showing the
model the unit's whole enclosing chapter/part (when it fits the resolved
role's `usable_context_tokens` budget, minus headroom for instructions/
glossary/local state/output/review metadata) or a bounded fallback window
expanding outward unit by unit. Every request keeps four layers separately
labelled, never collapsed into one blob: profile/style instructions,
persistent document state, current chapter source context, and local
translation state. A whole-chapter-in-one-request mode exists for
comparison (`build_whole_chapter_translation_request`) but is not the
default.

`document_state.py` (Session D's 2026-10-05 addendum) is a small, versioned,
append-only store of only the translation-relevant facts a later chapter may
depend on -- approved terminology, definitions, notation, character/
register/forms-of-address, recurring names/places, and explicitly-marked
unresolved ambiguities. It is not a Story Bible, not RAG, and never
accumulates chapter summaries. Every item carries explicit certainty
(`established`/`likely`/`unresolved`) and a source pointer back to the
exact chapter/unit/character span that introduced or last refined it; a
model-authored item can never be `established` -- only a human can promote
one. Updating a (category, label) key never overwrites the prior value; it
adds a new version, so every historical translation's recorded state
version/content stays reproducible even after later chapters add state.

Session G wired Session C's existing chapter-level QA into this store: the
chapter QA runtime prompt also asks for `STATE_UPDATES` (category/label/
value/certainty/source span); `review_qa.run_chapter_qa` parses and
grounds them exactly like its existing issue spans (an ungrounded span or
a model-claimed `established` certainty fails closed, `needs_human`,
never silently accepted); `document_draft.py` then runs
`document_state.find_conflicts` before committing -- a proposal that
contradicts an existing item is recorded (never silently overwritten) and
only the non-conflicting proposals are committed as the next document-state
revision, which the *next* chapter's translation requests then receive.
`tests/test_document_draft.py`'s `ChapterQAPersistentStateTests` exercises
this end-to-end against the ten scenarios named in the addendum (carrying a
scholarly term and a literary character register across chapters, a
grounded contradiction, certainty never promoted, historical reproducibility
of earlier chapters' recorded state version, and a rejected
unallowlisted "summary" category).

Known limitation: a single document's whole translation/review/chapter-QA
budget is bounded by one list-price ceiling shared by every stage and role
(`DocumentJobs._run_configured_mode`); a very long, multi-chapter book under
Thorough quality can exhaust it before every chapter's QA/state step runs,
in which case that remaining QA is skipped with a note rather than spending
past the configured cap.

## PDF/EPUB export and its limitations (Session X/G)

`export_pdf.py` reflows the canonical schema-2 structure into a fresh,
Hebrew-RTL A4 PDF, preserving node-kind hierarchy as visual style (title >
heading > body > note) -- not the original page layout/pagination. Notes/
footnotes render inline near their source position, not pinned to the
original page bottom. Images embed only when the caller separately supplies
raw bytes keyed by node id (the canonical schema itself carries no image
payload); tables/formulas have no dedicated layout and render as plain
text. Treat PDF output as a readable, structurally faithful re-typeset, not
a reproduction of the source document's pagination.

`export_epub.py` preserves the original EPUB archive byte-for-byte (package
metadata, CSS, images, nav/TOC, fonts) except for rewritten chapter text,
which is the higher-fidelity path when the input is EPUB. Session G's
`export_epub_from_document_structure` reconciles this exporter with the
canonical schema-2 structure (previously it only had its own, disconnected
`epub-structure@1` extraction, see `audit/current_state.md`'s prior
checkpoints): a unit spanning more than one original EPUB block --
segmentation.py only ever merges consecutive plain `paragraph` nodes, never
headings/lists/quotations -- has its translated text placed in the first
block only, recorded as a `units_merged_multiple_blocks` limitation, rather
than duplicating text or guessing a split. A block containing an image/
table/audio/video is left in its original language untouched rather than
risk losing the embedded media.

Both exporters are exercised by representative automated tests (synthetic
fixtures, mock/fake adapters) but have not yet been visually inspected
against real, complex scholarly/literary source documents -- in particular
real footnote/endnote layouts, multi-column or table-heavy pages, embedded
formulas, and mixed Hebrew-Latin running text. Treat current output as
software-construction evidence, not a visual-acceptance proof, until that
review happens on real documents. OCR (`scholarly_translation ocr-pdf`) is
a separate local CLI component (Gate 3, requires a local Tesseract
install); the simple document UI does not offer OCR -- a scanned PDF with
no extractable digital text is refused there with a clear message.
