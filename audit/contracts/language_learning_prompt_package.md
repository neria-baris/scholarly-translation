# LEARN-PROMPTS — delivery contract

Date: 2026-10-06. Inspected base: 3c698126f24ca037f7c24a2d99e120e19ec620e2.
Component: development prompt package, not runtime implementation.
Owns: LANGUAGE_LEARNING_PROMPTS_HE.md and prompts/language_learning/*.md;
conductor-only append-only audit entries and the checkpoint update.
Input: user's learning requirements and repository architecture/development rules.
Output: indexed, cross-linked conductor/shared-contract/A/B/C/D/runtime prompts.
User extension: include 500 frequency-based lexical candidates for each requested
language fr/de/es/yi/it, readable lists + provenance-bearing JSON + local reproduction
helper. Data license CC-BY-SA-4.0 retained; no product module/dependency change.
Status/uncertainty: ready for dispatch preparation; interfaces are proposed frozen
bootstrap requirements, not claims that new Python modules or HTTP routes exist.

Invariants:
- Separate learning window and data; existing Hebrew translations copied read-only;
  Hebrew EPUB upload supported; no new translation profile or product agents.
- Durable learner/language continuity committed by explicit "קראתי"; no mastery claim.
- Frequent-vocabulary/grammar seed with honest provenance; no linguistic critic.
- One generation model (Luna), deterministic planning/storage/validation.
- User explicitly authorizes >2 agents for this extension. At most three disjoint
  builder worktrees after a shared bootstrap; integration and UI routing sequential.
  Exception is scoped to this work, not a change to DEVELOPMENT_WORKFLOW.md.
- Creating prompts does not dispatch builders or authorize paid runtime calls.

Errors: broken local references, overlapping parallel ownership, conflicting
interfaces or missing user requirements prevent prompt-package acceptance.
Side effects: documentation/audit files only; no runtime, input or secret changes.
Acceptance: all local links resolve; per-builder read/write sets and handoffs agree;
negative/recovery/continuity acceptance specified; complete/staged diff checked;
clean verified documentation commit and known push status.
Out of scope: product implementation, source ingestion, language quality evaluation,
paid provider runs, executing workers, revising global policy or legacy audit cards.
