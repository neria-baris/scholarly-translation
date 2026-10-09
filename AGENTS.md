# Repository execution contract

The conductor is the primary agent: whichever agent the user is talking to directly in the current session (Claude Code, Codex/Sol, or another). It delegates scoped implementation to builder subagents where appropriate (see development controls).

Before substantial work, read the relevant sources of truth:

- [Gate specification and conductor workflow](prompt_codex_cli_astra_conductor_translation_build_he.md), including the standing audit/Git procedure.
- [Current development controls](DEVELOPMENT_WORKFLOW.md) for contracts, model escalation, checkpoints and audit events.
- [Development policy](policy_astra_conductor_claude_builder_he(1).md).
- [Runtime architecture contracts](ARCHITECTURE.md) for product boundaries, source handoffs, and the scholarly-first translation profile decision.
- [Translation model strategy](scholarly_translation_model_strategy_he(1).md).

Execution rules:

- Work in gate order under the central prompt's supervised-autonomy rule: advance after verified acceptance, tests, audit, a clean commit and known push status (see network-outage limit in development controls); pause only for genuine human decisions or blockers.
- Maintain append-only `audit/gate_history.md` and `audit/run_history.md`; preserve superseded results with timestamps and gate numbers. Update them before presenting a Gate Card.
- The conductor owns routine Git operations and verified commits after passed gates. Review complete and staged diffs, stage only intended paths, and leave a clean working tree at completed gates. Follow the detailed commit-receipt procedure.
- The user authorizes ordinary verified fast-forward gate pushes to `origin/main` at `https://github.com/neria-baris/scholarly-translation.git`, including the necessary remote checks. Destructive operations remain unauthorized; stop on divergence or unexpected changes. Never infer broader permission from a configured remote.
- Prefer deterministic, local and cheap tools before expensive models where appropriate. Avoid unnecessary model calls and implementation beyond the current gate.
- Never commit secrets, credentials, local inputs, caches or sensitive generated data.
- Read `audit/current_state.md` before resuming; update it at gate boundaries. Astra or Fable (Claude Fable) is an exceptional read-only adviser, only under the written escalation controls.
- If applicable instructions conflict, stop and surface the conflict rather than guessing.
