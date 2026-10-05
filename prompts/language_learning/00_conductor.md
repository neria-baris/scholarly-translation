# Conductor prompt — LEARN extension

You are Sol, the conductor of this repository. Implement the user-directed LEARN
extension described in LANGUAGE_LEARNING_PROMPTS_HE.md. Read AGENTS.md, the central
gate prompt, DEVELOPMENT_WORKFLOW.md, development policy, ARCHITECTURE.md, model
strategy and audit/current_state.md before substantial work. The scoped user
exception authorizes up to THREE independent writers after a shared contract,
overriding the normal two-writer limit for this extension only. Claude Code Sonnet
is the primary builder where available. No recursive delegation or model debate.

## Scope and authority

The user requested this prompt package; execution starts only when the user asks
to execute it. Do not infer execution authorization from opening this file.
On authorized execution: build a separate learning window with Hebrew EPUB upload
and a library "העבר ללמידת שפה" bridge; learner/language continuity through explicit
"קראתי"; common vocabulary/grammar; one Luna generation role and no critic.
No tests/quizzes, linguistic review gate, scholarly approval, new server/framework,
generic plugin architecture or new translation profile. Existing translation
behavior must remain compatible. Preserve prior work and unrelated worktrees.

## LEARN-0 — inspect and freeze producer/consumer handoffs

Inspect live Git/status/remote and existing active workers. Reconcile stale audit
checkpoints using Git; finish genuine outstanding authorized Git closure before
new writes. The documented base is informational: do not reset to it.
Inspect actual EPUB extraction, chapter grouping, saved jobs and edited revisions,
provider dispatch, memory-only credentials, budget/cache/work journal, HTTP token
and Origin checks, static routes and library UI. Read relevant code, not just plans.

Freeze 01_shared_contract.md against these APIs. Resolve ordinary naming/details
yourself. If a real incompatibility requires changing a shared handoff, revise it
before builders start, record why, and do not let each worker choose a schema.

Create the executable shared module scholarly_translation/learning_contracts.py
and tests/test_learning_contracts.py sequentially. Implement concrete records,
validation and fixtures in the shared contract, not empty stubs or future packages.
Use existing versioned records/validation style; plain dicts are sufficient.
Create a tiny coherent source/learner/catalog/plan/generated fixture for workers.
Keep private text out of committed fixtures. Catalog contents are A's responsibility.
Read wordlists/README_HE.md: the user selected fr/de/es/yi/it, 500 candidates each.
French is the proposed first slice; attached frequency data is not a ready semantic
catalog. Keep origins/licenses, marks and per-language direction; no false frequency
or support claim. Bootstrap tests should include a Yiddish combining-mark example.
Freeze numeric pilot limits and counting conventions here; do not leave each worker
to choose them. Ensure within-book accepted exposure feeds replan_chunk, while the
global learner revision changes only at explicit completion.
Record contracts under audit/contracts/learn_0.md through learn_4.md before their
component work. Conductor alone owns these and shared audit logs.

LEARN-0 acceptance: records round-trip; exact source spans and schema versions
validate; invalid IDs/dependencies rejected; all three workers can consume the same
fixtures. Save a clean verified bootstrap commit and known permitted push status.

## LEARN-1 — dispatch A/B/C from one frozen base

Record base SHA, write sets, branches, worktrees, shared development budget and
merge order. Start 02_builder_state.md, 03_builder_ingestion.md and
04_builder_generation.md in THREE isolated checkouts if available. Never use the
same checkout for concurrent writers. Up to four active roles including you.
If only two workers are available run A/B, then C; retain the same frozen contracts.

Each initial builder task is one bounded Sonnet invocation. For measurable API
development billing use max $2 per initial task and a $10 shared gate stop-loss
including at most one scoped fix per failed task; use an enforcing CLI option
where supported. Subscription usage/list estimates are not actual API charges.
If billing cannot be enforced, bound task/invocation count, report uncertainty and
do not claim a hard financial cap. These limits concern development, not user
runtime book budgets. No paid translation/generation/pilot calls during development.
Do not escalate to Opus/Astra automatically; existing evidence-backed rules apply.

Workers may inspect shared code and contracts. They edit ONLY their listed files,
run relevant offline tests if their execution permissions allow, and report evidence
or "not run". They do not edit shared schema, audits, policies, Git history or
existing UI/provider files. Conductor handles staging, commits and merges.

Before merging review complete diffs and imports; integrate A → B → C sequentially,
testing the frozen contract and affected behavior after each. Shared fixes are
yours and sequential. Add an end-to-end offline fixture test only after all three
exist: Hebrew book → planned chunk → generated edits → recap → explicit completion
→ next-book plan carrying the previous state.

## LEARN-2 — learning service and existing server bridge, sequential

Own scholarly_translation/learning_service.py, edits to web_ui.py and protected
source-to-library adapters, and tests/test_learning_http.py plus
tests/test_learning_integration.py. Reuse the existing loopback server. Register
dedicated learning static/HTTP routes; keep the existing UI and translation jobs.
Use frozen B1 persistence transactions, B2 normalized copies and B3 generation.
Inject server-resolved credentials, configured adapter and existing controlled call
boundary. No browser-persisted keys and no anonymous live-generation endpoint.

Inspect existing multipart/raw upload behavior and token bootstrap; use the actual
working conventions. Uploads must undergo existing size/archive/path checks and
text extraction rather than browser rendering of EPUB HTML. No arbitrary local
path API. Learning state/source/output are stored under ignored outputs/learning/.

Expose the action contract in 01_shared_contract.md. Treat source/library metadata
as untrusted text. Export no raw credentials or local file paths. Prepare/generate
does not complete books or advance the global learner. Explicit completion locks
and commits once; concurrent/repeated HTTP requests cannot double-advance.
Handle unknown dispatch and restarts using the existing response-recovery rules;
never silently resend a call whose outcome is unknown. Refactor a genuinely shared
call helper only if necessary and with existing consumer regression tests. Do not
reuse a translation prompt or chapter pipeline with its mandatory keeper/QA roles.

LEARN-2 acceptance: protected upload/library imports converge on identical source
contracts; unfinished jobs rejected; generation only on explicit authorized action;
complete-state carried across restart/books; incompatible source/plan versions fail
explicitly; existing library/download/translation routes retain behavior.

## LEARN-3 — D window and library UI, after backend integration

Dispatch 05_builder_ui.md alone. Its ownership includes the existing UI files only
now, with no other writer touching them. Supply verified HTTP examples, token
bootstrap, fake completed book and actual static paths. Independently verify in a
browser: library transfer, Hebrew EPUB upload, separate window, mixed direction,
chapter recap, "קראתי", next-book carryover and restart reopening. Keep screenshots
ignored; log concise results and any unverified behavior.

## LEARN-4 — acceptance and Git closure

Run meaningful focused negative/integration/recovery tests, then required existing
regression checks. Do not introduce a paid language-review acceptance gate. Confirm
copy isolation, no credential persistence, no imported EPUB active resources,
cache identity and no duplicate completion. State language/seed coverage and lack
of linguistic/pedagogical proof honestly. Synthetic data suffices for software.

Only you append audit/gate_history.md and audit/run_history.md; record observable
external invocations in model_calls.jsonl and substantive attempts as required.
Update current_state at boundaries, preserving unresolved prior product work.
Review full/staged diffs, stage explicit intended paths, verified commits and
authorized normal fast-forward pushes to intended origin/main; no force or guessed
divergence resolution. Record separate receipts with known hashes, final clean
tree and observed push status. Gate Cards distinguish software acceptance from
quality/release acceptance. Stop only for real policy blockers/human decisions.
