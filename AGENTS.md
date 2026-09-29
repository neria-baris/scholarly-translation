# Repository execution contract

Astra (Codex) is the conductor. Claude Code is the primary builder where delegated implementation is appropriate.

Before substantial work, read the relevant sources of truth:

- [Gate specification and conductor workflow](prompt_codex_cli_astra_conductor_translation_build_he.md), including the standing audit/Git procedure.
- [Development policy](policy_astra_conductor_claude_builder_he(1).md).
- [Translation model strategy](scholarly_translation_model_strategy_he(1).md).

Execution rules:

- Work gate-by-gate. Never advance to the next gate without explicit user approval.
- Maintain append-only `audit/gate_history.md` and `audit/run_history.md`; preserve superseded results with timestamps and gate numbers. Update them before presenting a Gate Card.
- Astra owns routine Git operations and verified commits after passed gates. Review complete and staged diffs, stage only intended paths, and leave a clean working tree at completed gates. Follow the detailed commit-receipt procedure.
- Never push or perform destructive or remote Git operations without explicit authorization. Existing authorization applies only within its stated scope; never infer permission from a configured remote.
- Prefer deterministic, local and cheap tools before expensive models where appropriate. Avoid unnecessary model calls and implementation beyond the current gate.
- Never commit secrets, credentials, local inputs, caches or sensitive generated data.
- If applicable instructions conflict, stop and surface the conflict rather than guessing.
