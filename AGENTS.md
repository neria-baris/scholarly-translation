# Repository execution contract

Astra (Codex) is the conductor. Claude Code is the primary builder where delegated implementation is appropriate.

Before substantial work, read the relevant sources of truth:

- [Gate specification and conductor workflow](prompt_codex_cli_astra_conductor_translation_build_he.md), including the standing audit/Git procedure.
- [Development policy](policy_astra_conductor_claude_builder_he(1).md).
- [Translation model strategy](scholarly_translation_model_strategy_he(1).md).

Execution rules:

- Work in gate order under the central prompt's supervised-autonomy rule: advance after verified acceptance, tests, audit, commit and synchronization; pause only for genuine human decisions or blockers.
- Maintain append-only `audit/gate_history.md` and `audit/run_history.md`; preserve superseded results with timestamps and gate numbers. Update them before presenting a Gate Card.
- Astra owns routine Git operations and verified commits after passed gates. Review complete and staged diffs, stage only intended paths, and leave a clean working tree at completed gates. Follow the detailed commit-receipt procedure.
- The user authorizes ordinary verified fast-forward gate pushes to `origin/main` at `https://github.com/neria-baris/scholarly-translation.git`, including the necessary remote checks. Destructive operations remain unauthorized; stop on divergence or unexpected changes. Never infer broader permission from a configured remote.
- Prefer deterministic, local and cheap tools before expensive models where appropriate. Avoid unnecessary model calls and implementation beyond the current gate.
- Never commit secrets, credentials, local inputs, caches or sensitive generated data.
- If applicable instructions conflict, stop and surface the conflict rather than guessing.
