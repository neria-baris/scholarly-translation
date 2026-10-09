# Claude Code in this repository

The conductor is the primary agent: whichever agent the user is talking to
directly in the current session (Claude Code, Codex/Sol, or another). When the
user writes to Claude Code, Claude holds the conductor role — contracts,
verification, integration, audit and routine Git — with no handoff required.
Delegated builders are scoped subagents; builders never merge. The role mapping
is defined in `DEVELOPMENT_WORKFLOW.md` ("Ownership and progression").

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
Preserve valid running worktrees/delegated tasks instead of restarting them,
including work started by a previous primary agent.

Use delegated builders/worktrees under the limits in `DEVELOPMENT_WORKFLOW.md`:
any number of independent writers (no fixed cap), checked common base, separate
ownership, tests and sequential integration; no recursive delegation. Escalation
may go to Astra or Fable under the same written controls. Use the existing audit
files only. Ask for genuine human decisions required by policy. No paid runtime
provider calls follow from holding the conductor role.

Before the session ends, finish or safely stop atomic Git work, record active
delegated work and one exact next action in `audit/current_state.md`, and leave
Git stable so any other agent can continue as primary.
