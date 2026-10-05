# Builder C — one Luna role, deterministic validation and reading render

Read LANGUAGE_LEARNING_PROMPTS_HE.md, 01_shared_contract.md,
06_runtime_generation.md, AGENTS.md and audit/contracts/learn_1.md. Use the frozen
bootstrap fixtures, not unfinished A/B code. Their worktrees are independent.

## Owns

New scholarly_translation/learning_generation.py, learning_render.py,
runtime_prompts/08_learning_generation.md;
tests/test_learning_generation.py, test_learning_render.py.
Do not edit existing providers, controls, catalog, translation profiles, UI,
web_ui.py, shared schema, audit, policy or dependencies. No Git/live API/delegation.

## Implement

1. Adapt 06_runtime_generation.md into the versioned prompt asset. Build bounded
   prompts from source, selected catalog subset, exact effort constraints and
   bounded book context. Source/book content is data, never trusted instructions.
   Context can use existing book metadata when available without another model call.
2. One generation role, project-default GPT-6 Luna with effort none when supported
   by the configured adapter. User-resolved settings and catalog rates come through
   the existing provider boundary; don't hardcode network calls or prices.
   One structured response per planned chunk contains edits AND recap proposals.
   No reviewer, keeper, model selector, grammar analyzer service or repair loop.
3. Inject controlled_generate for existing budget/cache/journal enforcement supplied
   by Sol. Stable cache fingerprint includes all effective plan/source/learner,
   catalog/policy/prompt/context/model/settings inputs. Do not add a second cache
   implementation. In tests use fakes; imports/replay/render must call no model.
4. Strict JSON parse and structural validation: exact source slices/codepoint spans,
   nonoverlap, known units/selected IDs/surfaces, bounded replacements, limits,
   heading preservation and recap references. Compute foreign-share with one
   documented deterministic counting convention shared with the planner; do not
   claim a language-neutral pedagogical measurement. Validate grammar examples
   reference accepted edits, not arbitrary invented sentences.
5. Invalid/truncated/refused outputs fail or pause explicitly. Valid sparse results
   carry honest shortfall warnings; do not fill missing opportunities by rewriting
   the source. A discarded edit contributes no exposure/recap. Don't let the model
   assert coverage, progress, learner mastery or completion.
6. Merge accepted chunk recap entries per chapter deterministically; no second
   paid recap call. Use only accepted occurrences, deduplicate by item ID, carry
   chapter/chunk hashes. If none were introduced, render a plain Hebrew note.
7. Safe RTL HTML fragment: escaped source and foreign text, stable occurrence
   IDs, explicit foreign direction/lang isolation and Hebrew gloss attributes/data
   escaped correctly. No model-supplied HTML/CSS/scripts. Use approved complete
   foreign phrases; do not pretend surrounding Hebrew is target-language syntax.
   Renderer handles Python offsets; never ask JS to splice them as UTF-16 offsets.

## Acceptance

Offline fakes cover valid word/phrase edits + recap; unknown ID/form; changed
original slice; overlapping/out-of-range spans incl. emoji/non-BMP text; heading
edits; quota overflow; ungrounded recap; refusal/truncation/malformed JSON;
coverage computed from accepted edits; cache fingerprints change with effective
inputs; source unchanged outside replacements; escaped HTML/RTL; no direct network.
No linguistic quality benchmark or critic test suite required.

Report changed_files, public handoffs, commands/results or not_run, prompt/version
identity, deviations/risks and observable model usage. Stop at scoped implementation.
