# LEARN-5 — optional click gloss, scoped verification and expansion direction

User steering 2026-10-06 permits a meaning revealed by a deliberate click while
retaining no automatic adjacent translations. User also prefers eventual
model-chosen vocabulary beyond500 and asks why other languages are unavailable.

Component: reader display only. Owns optional click presentation, not curriculum.
Input: existing accepted GeneratedChunk schema1 and Hebrew gloss; read endpoint
adds optional boolean gloss_on_click, default false for backward compatibility.
Output: escaped focusable foreign occurrences when explicitly requested, hidden
separate meaning panel revealed only by click/Enter/Space. Reader checkbox enables
this option initially; checkbox off returns context-only text. Escape/close dismiss.
Invariants: no inline/automatic gloss, no model call, no source/content hash or
learner/effort change, no HTML from gloss, legacy prepared content readable.
Errors: nonboolean gloss_on_click -> invalid_learning_request.
Side effects: display request and existing cursor save only. Main checkout/server
and concurrent edits stay untouched; isolated preview may reload its own process.
Acceptance: renderer escaping/direction, service opt-in/hash/call invariants,
UI wiring/syntax and synthetic browser click/close/keyboard/disabled behavior.
Run affected learning render/UI/cumulative/HTTP tests; full suite not needed since
no provider, cache, budget, completion schema or translation behavior changes.
Out of scope for this small correction: enabling languages or runtime proposals.
Those are architectural answers here, not an unrequested larger implementation.

Accepted direction for subsequent vocabulary extension: a single generation call
may propose bounded new lexical entries with stable application-assigned IDs,
language/sense/forms, source-linked occurrences and model/prompt provenance.
Validate structure/spans/quotas; admit only entries used by accepted edits; retain
book-local definitions for replanning/reader/resume and promote them exactly once
on explicit completion. Existing items cannot be redefined by a later response.
Keep common frequency seeds and model instructions; no fixed500 ceiling, separate
critic, glossary model or hardcoded multilingual500-translation requirement.
The same mechanism can serve fr/de/es/yi/it; yi needs RTL and combining-mark care.
Software validation is not linguistic review. Current parser remains closed until
this proposal/persistence contract is implemented and verified together.

Implementation: Sol direct small fix, no external builder/critic/runtime calls.
Git: reviewed isolated feature commit/receipt only, push not attempted, no main
merge/deploy while active translation and unrelated main edits remain in progress.
