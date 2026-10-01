# Local UI shell contract

- Component/owner: local browser shell, requested by the user on 2026-10-01; Sol owns integration and verification.
- Input: selected existing CLI command, user-chosen local file paths/options and a new output directory. Settings may include one session-only OpenAI key and nonsecret provider, language, OCR and budget choices. No credentials are persisted.
- Output: existing CLI artifacts and exit status; matching source/draft preview and latest artifact path for browser/file viewing. The UI does not change persisted product schemas or grant approval.
- Invariants: invoke `sys.executable -B -m scholarly_translation` with an argv list and no shell; default provider is mock; OpenAI needs explicit in-window confirmation for each run; a session key is passed only through the child environment, never argv, response or disk; each default output directory is unique; failed commands do not advance output paths. Preview pairs a draft only with its exact document/unit/source-text identity.
- Errors: required fields, invalid choices and pages are rejected before subprocess start. CLI validation remains authoritative. Missing Python/dependencies are reported by the launcher.
- Side effects: loopback-only local HTTP server and CLI writes under user-selected output paths, default ignored `outputs/ui`; optional browser opening of local generated files. No external network service or automatic paid request.
- Acceptance: launcher finds a working local Python, the page and settings open, mock demo and path handoff run, generated HTML can be opened, session key is not echoed, stale draft is not paired, command construction and full existing tests pass. Real PDF/source/translation quality and Gate-10/11 acceptance remain separate.
- Out of scope: replacing JSON decision editors, changing source/approval policy, embedding provider credentials or altering Gate-11 runtime controls.
