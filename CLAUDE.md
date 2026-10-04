# Continuity bootstrap for this integration run

Sol/Codex remains the normal conductor; Claude Code remains the primary builder.
Only on an explicit continuity handoff for this run may Claude temporarily assume
the Sol conductor responsibilities: contracts, verification, integration, audit
and routine Git. This is not a permanent policy change. Builders never merge.

Read in order before substantial work:
1. `AGENTS.md`
2. `DEVELOPMENT_WORKFLOW.md`
3. `policy_astra_conductor_claude_builder_he(1).md`
4. `prompt_codex_cli_astra_conductor_translation_build_he.md`
5. `ARCHITECTURE.md`
6. `scholarly_translation_model_strategy_he(1).md`
7. `audit/current_state.md`
8. `audit/claude_integration_conductor.md` (authoritative remaining D/X/F/G prompts).

A/B/C/E were already implemented; do not reimplement them. Git and
`audit/current_state.md` govern live state. Inspect status, remotes, branches,
worktrees and the decorated all-branch graph yourself; reconcile the checkpoint
with Git, then continue its exact next action. Git governs any discrepancy.
Preserve valid running worktrees/delegated tasks instead of restarting them.

Use delegated builders/worktrees under the SAME limits in
`DEVELOPMENT_WORKFLOW.md`: at most two independent writers, checked common base,
separate ownership, tests and sequential integration; no recursive delegation.
Use the existing audit files only. Ask for genuine human decisions required by
policy. No paid runtime provider calls or policy changes follow from takeover.

For return to Sol, finish or safely stop atomic Git work, record active delegated
work and one exact next action in the same checkpoint, and leave Git stable.
