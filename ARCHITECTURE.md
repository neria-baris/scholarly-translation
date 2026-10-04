# Runtime architecture contracts

Status: proposed pre-Gate-4 boundary map, prepared from clean main at
a5aa8f82598d477820a7a6ebeeeeb846e233c3db on 2026-09-30. Gates 1-3
are accepted and synchronized; Gate 4 has no contract or implementation.

## Scope and authority

This file is the shared source of truth for runtime component boundaries,
ownership, handoffs and dependency rules. The central gate prompt defines
milestone outcomes; DEVELOPMENT_WORKFLOW.md and the development policy define
how work is contracted and accepted; the model strategy defines runtime quality,
routing and cache policy. Local contracts in audit/contracts/ specify each Gate.
Implemented Python records and validators govern exact persisted field shapes
and schema compatibility. If an implemented schema and this map disagree, report
the difference and resolve it explicitly at a Gate; do not silently reinterpret
persisted data.

This map fixes only interfaces whose stability protects adjacent Gates. It does
not prescribe internal classes, parsing algorithms, providers, prompts, routing,
UI implementation or a future service architecture.

## Runtime flow

Original PDF
  -> digital extraction and/or selected-page OCR
  -> retained source evidence
  -> source reading and structure resolution, including human action if needed
  -> versioned translation segments linked to exact source evidence
  -> selected translation profile resolves applicable terminology and bounded context
  -> provider-independent translation request and draft
  -> deterministic findings and conditional semantic findings
  -> bounded correction and human resolution
  -> approval state and bilingual export

Development orchestration (Sol, Claude, tests, Gate, audit and Git) is outside
this runtime flow.

## Boundaries and handoffs

| Boundary | Owner and output | Required input / consumer | Must not do |
| --- | --- | --- | --- |
| Digital extraction | Produces a schema-3 Document with page text, extracted lines, exact character spans, page geometry, PDF hash and source status. | Original PDF bytes and language; consumed by source resolution and selected-page OCR. | Infer scholarly meaning, silently repair text or claim layout approval. |
| OCR | Produces a separate evidence bundle with selected-page image, transcription, word spans/boxes, engine identity and uncertainty. Gate 3's committed bundle schema is 1. | Schema-3 extraction and byte-identical PDF; consumed by source resolution and human inspection. | Overwrite extracted source, decide that OCR is correct, or make unreviewed OCR eligible for automatic translation. |
| Source reading and structure | Chooses an inspectable reading from digital/OCR evidence or returns unresolved with reasons; retains every source alternative and its evidence link. | Extraction and any OCR bundle; consumed by segmentation and human review. | Manufacture a valid-looking reading for ambiguous text, reading order, footnotes, citations or formulas. |
| Segmentation | Produces versioned translation units with stable IDs and exact links to source reading/evidence; preserves prior-version links when boundaries change. | Readable source and structure; consumed by terminology, translation, checks and review. | Translate or decide glossary policy. |
| Terminology / approved memory | Produces applicable approved rules and explicit proposals with scope and version. | Segment and human-approved terminology; consumed by translation and invalidation. | Approve loaded scholarly terms by model output alone. |
| Translation | Produces a draft and observable provider/model/prompt/terminology provenance. | Segment, source language, applicable rules and bounded context; consumed by checks and review. | Mutate source, change terminology policy or grant human approval. |
| Checks and conditional semantic review | Produce distinct formal findings and source-to-target semantic claims, with versions and spans where available. | Source plus draft; consumed by correction and human review. | Treat valid structure, model confidence or a passing contract test as proof of meaning. |
| Human resolution and export | Human action resolves disputed source/terminology/translation and records approval; export renders the chosen version with source links. | Evidence, draft, findings and approval state. | Let export silently correct text or display unresolved work as approved. |

A component may return an explicit unresolved/error outcome. Uncertainty is data,
not an exception to be hidden by filling required fields with guesses.

## The Gate 3 to Gate 4 source handoff

The committed schema-3 Document is digital extraction evidence. Its current
Segment objects are extracted lines, not automatically the translation units
required by Gate 4. The committed OCR bundle is separate evidence and currently
has no validated reader or promotion path into a translation-ready source.
Gate 4 must establish that producer-consumer handoff before it creates
translation units from OCR pages. It must not retrofit OCR text into the original
Document or treat a matching page_id alone as source approval.

The minimum handoff must preserve: document and page IDs; original PDF hash and
location; selected source reading and its version/hash; exact text span or
equivalent image/word location; evidence origin (digital or OCR); image reference
for OCR; and explicit unresolved reasons. Exact Python type names and serialized
field layout belong to the Gate 4 contract and implementation. For unresolved
OCR, no ordinary translation request may be created. An experiment on unresolved
source must remain visibly unapproved and cannot be exported as approved work.

A translation unit needs its own stable ID/version and a link to the previous
version when a boundary is corrected. It may cover several extraction lines or
part of one. Its source link must be verifiable against the selected reading and
the retained PDF/image evidence. Source evidence is immutable; corrected
readings, segments and translations are derived records.

## Model and prompt boundary

The Gate 1 mock adapter currently accepts text and target language and returns
a string. That is a substitution demonstration, not the final product contract.
At Gates 6-7, a translation request should carry profile_id, a translation unit, language,
applicable terminology, bounded context and source/version references. A
provider adapter builds its provider-specific prompt/request, parses the raw
response and returns a structurally validated draft plus observable usage and
model/prompt identity. Review follows the same boundary with a source/draft
request and span-linked findings. Prompt text and provider choice are versioned
implementation or configuration; neither defines core source records. A
provider abstraction is useful at that call boundary; it is not a reason to
abstract every deterministic source operation.

## Translation profile decision

The pipeline remains scholarly-first, but the generic translation, provider and
result path must not bake scholarly context or quality rules into its interface.
A translation profile is the policy selection at the orchestration boundary.
No profile runtime code exists yet. The first implementation will support only
profile_id = scholarly; no second profile, registry, plugin framework or
literary feature is introduced by this decision.

A future profile could resolve a different context-building policy,
terminology policy, quality/review policy and prompt/config selection while
reusing the same generic translator, provider adapter, result/provenance and
cache mechanisms. The profile owns policy selection; it does not own source
extraction, source correction, provider transport or human approval. The
scholarly-first policy and Gate order remain the active plan.

When a TranslationJob is introduced, it selects exactly one profile_id and
requests inherit it. If no job object exists, TranslationRequest carries the
selection directly. A request must carry the immutable profile_id (initially
scholarly) alongside its segment, source language, applicable context and
terminology. The translator receives already resolved policy inputs; the
provider adapter receives the resolved provider request and must not contain
scholarly-specific branching. Unsupported profile IDs fail explicitly rather
than falling back silently to scholarly.

Persist profile_id on translation results and provenance, together with the
effective context, terminology, review and prompt/config revisions or a
reproducible fingerprint of the applicable resolved policy. Record only
revisions that actually affect that artifact. Prompt selection is keyed by
profile_id plus a prompt/config version; prompt wording remains outside the
core request/result schema. For translation cache identity, include profile_id
and the effective profile policy/prompt revisions in addition to source span,
neighbor, applicable glossary, model and decoding inputs. Review cache identity
also includes profile_id and effective review criteria version. A policy
revision invalidates only affected derived artifacts. Merely adding a new
profile does not invalidate approved scholarly results.

Gate 4 source/segment contracts need no profile field: source evidence and
segmentation are generic. Gate 5 may define scholarly terminology behavior
without a profile registry. Gates 6-7 should introduce the one supported
profile_id when a real translation request/job and persisted result appear.
Gate 8 should use the resolved review policy. Test that the scholarly selection
reaches request, result, provenance and cache key, and that an unknown ID is
rejected. Do not build literary translation, EPUB input, Story Bible, character
memory, style models or speculative policy interfaces in these Gates.

## Dependency and invalidation

Store direct provenance/dependency references on derived artifacts; a workflow
engine, event bus or global rebuild is unnecessary. Changing a source reading
(including accepted OCR) invalidates affected segments and their downstream
translations/reviews. Changing a segment boundary invalidates that segment's
dependent outputs and preserves the old version link. Changing a glossary rule
invalidates only translations for segments in its applicable scope. Changing a
translation invalidates its review; changing only UI does not invalidate
translation. A profile or resolved policy change invalidates only outputs
that depend on the changed policy; profile_id prevents cross-profile cache
reuse. A model update does not revoke an already human-approved translation
by itself; it may trigger sample re-evaluation. See the model strategy for the
existing cache-key policy. Add concrete keys only when their producing and
consuming artifacts exist.

## Verification and deferred decisions

Deterministic validation covers IDs, hashes, parent links, source spans, geometry,
schema/version compatibility and dependency-key changes. Integration tests cover
digital and OCR evidence through source resolution and segmentation, including
unresolved and changed-boundary cases. Semantic review may identify a possible
meaning error with evidence; a human decides uncertain reading, footnote
association, loaded terminology, unresolved translation and final publication
approval. A valid schema is not semantic correctness.

Gate 4 must test both a digital page and an OCR page reaching a source-linked
translation unit, and an ambiguous OCR page remaining unresolved. Gate 5 owns
term scope/version. Gates 6-7 own the first real translation request/result
shape. Gates 8-9 own review findings and approval/export details. Gate 10
measures model/routing quality. Do not freeze those later field sets, provider
choices, prompt wording, OCR thresholds, Japanese layout heuristics or context
window sizes before their Gate or real-source experiments. Only scholarly is
planned for the first implementation; future profile behavior remains deferred.

## User-directed simple document flow (2026-10-04)

The user explicitly requested PDF/EPUB upload, automatic translation/download
and optional review. This independent UI extension, scoped by
`audit/contracts/ui_simple.md`, adds EPUB text input for that product flow;
prior Gate-specific deferrals above remain historical descriptions of those
Gates. It introduces no literary profile, glossary approval shortcut or OCR.

`document_draft.py` owns bounded embedded-text PDF/EPUB-spine extraction,
source spans/hash, model/effort requests, durable Gate-11 reservations/cache,
job progress/recovery and optional edited revisions. `web_ui.py` exposes these
through token/origin-guarded loopback endpoints; `ui.html/css/js` present upload,
secondary settings, results/download and optional source/target editing.

Schema-1 `document-draft@1` is deliberately separate from canonical scholarly
translation/review/export schemas. Its `approved` and `source_reviewed` are
always false. HTML/TXT outputs are labeled automatic drafts, including partial
results; human edits preserve prior revisions and never grant research approval.
Completed results can resume after server restart; in-flight interrupted jobs
cannot silently dispatch again. No network call occurs in demo or tests.
