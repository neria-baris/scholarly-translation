# AUTOMATION-1 — model-aware accounting and local token counting

Authorized: user execution instruction and 2026-10-05 cost/model/key addendum.
Base: e333fd3 (Session G closed). Owner: Sol; scoped builder: Claude Code Sonnet.

Component/owns: secret-free model catalogue/pricing, deterministic token sizing,
provider usage normalization and per-call accounting. Inputs: existing schema-1
model configuration, Unicode prompts, observed provider usage. Outputs: dated
rate provenance, explicitly labelled estimates, token count method/uncertainty,
validated incomplete-response statuses and shared-document budget events.

Invariants: preserve existing config/SQLite readers and diagnostic defaults;
never charge arbitrary models at Luna prices; cache discounts only on observed
cache usage; include cache creation/read in Anthropic input totals; reasoning
is included in provider output, never charged twice. Unknown tariff uses an
explicit labelled estimate with a conservative configurable rate assumption.
No keys in persistent artifacts. A role's output cap is its call cap, while
the shared task cap remains a policy ceiling. Unknown dispatch retains its hold.

Errors: invalid limits/rates/usage, missing credentials, oversize and truncated
responses fail explicitly. Side effects: local token encoding cache and existing
SQLite controls only; no live generation/automatic paid pilot.

Acceptance: mixed Hebrew/Japanese/Latin deterministic sizing, no word-count
claim of conservatism, model-specific normal/long-context/cache costs, per-role
caps under one document, unknown model labelled estimate, SDK substitute tests
for truncation/cache/reasoning/key injection, existing tests pass.

Out of scope: UI, chapter planner/recovery/correction, human quality acceptance,
export layout. These follow in separate dependent slices.

Builder budgets: API runtime USD 0; one subscription invocation; CLI maximum
budget USD 10 where enforceable; wall soft 20 minutes; tool soft 80; no recursive
delegation/Git/audit edits. Subscription charge/quota unknown, list estimate
recorded separately. One targeted repair after a failed attempt before reassessment.

Official sources checked 2026-10-05:
- https://developers.openai.com/api/docs/models/gpt-6-luna
- https://developers.openai.com/api/docs/models/gpt-6.1-sol
- https://platform.claude.com/docs/en/models/sonnet-5-5/overview
- https://platform.claude.com/docs/en/models/opus-5-5/overview
- https://github.com/openai/tiktoken
- https://platform.claude.com/docs/en/build-with-claude/token-counting

Tiktoken's current published mapping does not identify GPT-6: fallback encoding
must be labelled an estimate, not exact model counting. Provider-specific remote
count endpoints are optional; offline execution always has a deterministic
bounded fallback. No remote token counting without an explicitly supplied key.
