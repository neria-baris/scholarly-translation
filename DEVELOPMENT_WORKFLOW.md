# Current development controls

User-authorized development update, 2026-09-30. This supplements the central gate specification and development policy; the product's runtime quality/routing strategy is unchanged. Historical audit cards are never rewritten.

Role update authorized by user on 2026-10-09: the conductor is the primary agent the user is talking to directly in the current session, whatever its vendor or model (Claude Code, Codex/Sol or another). No handoff is required for an agent to hold the role. Where current policy documents say "Sol" for the conductor role, read "the conductor"; historical audit records that name Sol stay as written.

Update authorized by user on 2026-10-09: escalation may go to Fable (Claude Fable, normally claude-fable-5-1) as well as Astra, and the fixed limit of two parallel builders is removed. All other parallelism and escalation controls remain.

Gate-11 extension authorized by user on 2026-10-01: persistent budget, cache and usage controls may proceed and receive scoped software acceptance independently while Gate-10 human quality evaluation remains preliminary/BLOCKED. Contract: `audit/contracts/gate_11.md`. This does not establish quality, choose a model or authorize release. The earlier gate-order rule remains for dependent work; this explicit independent extension is the exception.

## Ownership and progression

The conductor (the primary agent, see above) owns gates, contracts, verification, integration, audit and routine Git. Small direct fixes are allowed when delegation adds no value. Delegated builders are scoped subagents, by default Claude Code Sonnet; Opus is for demonstrated implementation difficulty under a settled contract. No recursive delegation or model debate; one owner, one focused fix by default, at most one evidence-backed rebuttal.

Advance in gate order after a working public interface, contract/negative/integration tests, no defect in dependent contracts, documented evidence/limitations/cost, reviewed diff, clean commit and known push status. Gate Cards remain mandatory; routine transitions require no user response. Synthetic/permissibly sourced fixtures suffice for software construction. Real OCR/translation quality, gold judgments and model selection remain preliminary/BLOCKED until genuine examples and human judgment exist.

Stop for scholarly meaning/source/glossary decisions, actual pilot inputs, required credentials, cap increases, substantial scope changes, destructive Git/divergence, or final quality/release acceptance. Continue only independent work when a component is blocked. Never activate a paid runtime provider merely because a development CLI is authenticated.

Normal verified fast-forward gate pushes to the configured intended origin/main remain authorized. Review complete and staged diffs; stage explicit paths. Unexpected changes/divergence block that Git operation. No force-push, shared-history rewrite, branch deletion or guessed reconciliation. Temporary network failure is `not_synced`, not a code-test failure; warn before accumulating more than one additional gate without remote backup.

## Contracts and data

Before a component, write a concise contract under `audit/contracts/` with: component, owns, input (type/version/source references), output (type/version/status/uncertainty), invariants, errors, side_effects, acceptance, out_of_scope. Check producer and consumer and adapter substitution. Prefer pure typed logic; isolate files/OCR/APIs. No empty future packages, server, microservices, generic plugins or product-agent orchestration.

Minimal data spine: stable document/page/region/segment IDs; source location/language; stage ID/version; relevant input hash; warnings/status. Model-derived records add provider/model/prompt/glossary versions and observable usage. Derived data never overwrites source. Segmentation changes preserve prior-version links. Extend schemas only for current needs, with explicit legacy reading or migration.

Parallel isolated writers (no fixed count; open only as many as the work genuinely splits into), only after a checked shared contract: separate paths/branches/worktrees, common base, independent tests and merge order. Shared schema/config changes and integration stay sequential. Only the conductor writes shared audit logs.

## Strict escalation (Astra or Fable)

The escalation adviser — Astra or Fable (Claude Fable, normally claude-fable-5-1), chosen by the conductor per case — is an exceptional read-only adviser: no gate ownership, edits, delegation or PASS. Use preselected excerpts if effective read-only tool permissions cannot be guaranteed. Deterministic checks/documentation/small experiments precede escalation. A written case is mandatory and must satisfy one trigger:

1. A hard-to-reverse decision changes at least two active contracts, persistent format or future-gate validity, unresolved by documentation and a small experiment.
2. A material provenance/identity/formula/citation/cache/budget/permission flaw survives two distinct documented repair hypotheses and tests.
3. Independent results conflict on core correctness and a small deterministic test cannot resolve them.
4. A specific serious cross-component scenario remains without a discriminating test after code-path examination.

Case fields: issue_id, trigger, consequence, files/commit, tests, attempt IDs, two alternatives, exact question, effect of each answer. Send only the case and necessary excerpts. The conductor verifies the short evidence/uncertainty/test answer and decides. One escalation call (Astra or Fable) per issue; at most two per gate for distinct issues; the quotas count both advisers together. Same-issue repetition needs new evidence and user approval. After three cumulative calls, summarize verified value/cost and stop automatic escalation pending user decision. Opus and an escalation adviser, or Astra and Fable, are not both called on one question without new evidence. Routine failures, Git, missing input or ceremonial approval are not triggers.

## Audit, budgets and checkpoint

`audit/gate_history.md` and `audit/run_history.md` are concise append-only records. Add timestamps and gate/task IDs; preserve superseded results. Update records before presenting a card. Do not log every terminal command.

- `audit/model_calls.jsonl`: one event per observable external invocation: ID/time/gate/task/parent/interface/requested+actual+auxiliary model/purpose/input scope+hash/tokens+cache/duration/execution result/list estimate/actual charge/verified value. Do not invent internal CLI call breakdowns. Conductor cumulative usage is recorded only where observable; otherwise unknown.
- `audit/attempts.jsonl`: substantive attempt ID/issue/hypothesis/evidence/performer+model/diff or command/expected+observed outcome/keep-revert-revise. Repeating a test without a new hypothesis is not another attempt.
- `audit/current_state.md`: replaceable checkpoint, approximately 500 words maximum: current gate/latest known commit/contracts/open issues/blockers/remaining quotas/next action. Read it on resumption; after PASS remove resolved issues. Commit hashes are recorded in the next audit update or short receipt, never self-referentially.

Cards link IDs/evidence and summarize counts by conductor (with its model)/Sonnet/Opus/Astra/Fable, elapsed time and known/unknown costs. Default evidence is summaries; timestamped audit/raw files only for necessary irreproducible evidence, without full prompts, private source text, secrets or environment values. Existing historical evidence remains preserved.

Use policy stop-loss $2/$10/$30 for measurable tiny/normal/complex API tasks or lower contractual caps. Subscription turns/quota/time and list-price estimates are separate from actual charges. Do not claim a hard spending cap without an enforcing mechanism; bound tasks/calls when billing is unknown. Stop measurable spending at its cap; a failed attempt gets one scoped fix/retest before reassessment. Before another model call, check whether a deterministic test/cache/removing the call gives the same decision.

Cleanup only after verified Git closure: exact-path temporary build/reproducible cache/uncommitted experimental output that feeds no test or gate. No broad cleanup or git clean -fdx; never delete policies, code, tests, contracts, commits, cards or material evidence.
