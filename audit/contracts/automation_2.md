# AUTOMATION-2 — planned chapter processing and resumable local work

Authorization/base: user-approved AUTOMATION_WORK_PLAN_HE.md; depends on
verified AUTOMATION-1. Owner Sol; builder Claude Code Sonnet, one scoped call
USD10 where enforceable, runtime provider USD0, 30min soft, 120tool soft.

Owns: chapter planning, batched draft generation, controlled QA/correction,
durable step journal and document-job pause/resume. Input: canonical schema-2
structure with stable units/source spans, glossary/state, validated role config,
quality mode and document budget. Output: immutable plan fingerprint, ordered
unit-to-target mappings, per-role count/cost plan and observable draft status.

Invariants: no guessed scholarly approval/source repair. Units covered exactly
once in translation and QA targets; overlap is context only. Prefer whole chapter
when translator input/output and independent QA budget fit; otherwise consecutive
semantic unit batches, no arbitrary 2000char ceiling. Larger mode is labelled
experimentally unvalidated for scholarly quality. Count actual Hebrew before QA;
repartition QA as necessary. Required QA roles missing fail before translation;
fast deliberately disables semantic QA. Plan the price of QA, one bounded repair
and focused recheck before consuming translation budget, assuming cache misses.
Source, decisions and prompt versions bind the plan/results; invalidation only
recomputes dependent steps. No repeated generation for completed valid results.

Provider prefix: stable chapter source/IDs/profile/approved glossary precedes
dynamic targets/state. Expose a cache breakpoint to supported providers; maintain
local result reuse independently. No paid cache warming/keepalive. Cache savings
are observed, never guaranteed. Unsupported provider caching is explicit.

Recovery: persist planned/dispatched/received/validated/completed/unknown steps.
Persist received raw response before parsing; restart may validate/reuse without
another provider request. An unknown dispatched outcome blocks duplicate sending.
Pause finishes the in-flight step then stops before another request. Resume uses
same source/settings/plan and newly supplied memory-only credentials. Finite
attempts; one repair then recheck, unresolved error surfaced for human review.
Never export a missing target as if it were a translation.

Errors: source/config change invalidation, cap/context failure, missing/duplicate/
unknown mapped ID, malformed response, over-budget, uncertain dispatch or schema
corruption. Side effects: local original upload + job/journal/raw/cache artifacts
under ignored outputs; bounded chosen providers only after existing consent.

Acceptance: chapter fits translator but not QA; full chapter vs split coverage;
actual Hebrew changes QA partition; QA funds cannot be spent by translation;
unknown dispatch blocks resend; restart/raw reparsing and completed-step replay
call provider zero times; pause/resume; incorrect IDs/truncation rejected;
one repair with grounded issues and focused recheck; unapproved state preserved;
PDF+EPUB exports use current targets; legacy artifacts remain readable.

Out of scope: real quality gold/pilot without input/keys/consent; release approval;
arbitrary source splitting that loses lineage; external product-agent framework.
